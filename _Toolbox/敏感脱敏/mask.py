#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mask.py —— 文档转文本 + 规则驱动脱敏（一致性伪名化）

规则来源固定：只读本目录下的 规则/*.json，绝不从待处理文档中提取规则。
屏幕只打印统计，不回显任何原文。

用法:
    python mask.py --src <输入目录或文件> --out <输出目录> [选项]

选项:
    --rules DIR   规则目录（默认与本脚本同目录的 规则/）
    --force       忽略缓存强制重跑
    --dry-run     只统计不写文件
    --no-map      不输出映射表

输出（写到 --out）:
    [类型_序号].txt   脱敏后的文本，文件名本身也脱敏
    _stats.json       统计（不含原文）
    _map.tsv          原名 -> 脱敏名 的对照（任务结束应删除）

依赖:
    必需: python-docx, python-pptx
    可选: pymupdf（处理 PDF）
"""

import argparse
import calendar
import json
import re
import sys
import time
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass

try:
    from docx import Document
except ImportError:
    Document = None
try:
    from pptx import Presentation
except ImportError:
    Presentation = None
try:
    import pymupdf
except ImportError:
    pymupdf = None

TEXTIVE = {'.txt', '.md', '.csv', '.json', '.log'}
OFFICE = {'.docx', '.pptx'}
GAP = r'[\s（）()\[\]【】·\-—]{0,2}'
ZERO_WIDTH = dict.fromkeys(map(ord, '\u200b\u200c\u200d\u2060\ufeff'), None)
LAYER_ORDER = {'精确': 0, '模式': 1, '语义': 2}

# ---------------------------------------------------------------- 校验器
ID_W = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
ID_C = '10X98765432'
UC = '0123456789ABCDEFGHJKLMNPQRTUWXY'
UW = [1, 3, 9, 27, 19, 26, 16, 17, 20, 29, 25, 13, 8, 24, 10, 30, 28]


def id18_valid(s):
    if len(s) != 18 or not s[:17].isdigit():
        return False
    try:
        y, m, d = int(s[6:10]), int(s[10:12]), int(s[12:14])
    except ValueError:
        return False
    if not (1900 <= y <= 2099 and 1 <= m <= 12) or d < 1 or d > calendar.monthrange(y, m)[1]:
        return False
    return ID_C[sum(int(c) * w for c, w in zip(s[:17], ID_W)) % 11] == s[17].upper()


def uscc_valid(s):
    s = s.upper()
    if len(s) != 18 or any(c not in UC for c in s):
        return False
    return UC[(31 - sum(UC.index(c) * w for c, w in zip(s[:17], UW)) % 31) % 31] == s[17]


def luhn_valid(s):
    ds = [int(c) for c in s if c.isdigit()]
    if not (12 <= len(ds) <= 19) or len(set(ds)) == 1:
        return False
    t = 0
    for i, d in enumerate(reversed(ds)):
        if i % 2:
            d *= 2
            if d > 9:
                d -= 9
        t += d
    return t % 10 == 0


VALIDATORS = {'none': lambda v: True, 'id18': id18_valid, 'uscc': uscc_valid, 'luhn': luhn_valid}


# ---------------------------------------------------------------- 规则
def load_rules(rule_dir: Path):
    rules = []
    for path in sorted(rule_dir.glob('*.json')):
        try:
            data = json.loads(path.read_text(encoding='utf-8-sig'))
        except Exception as exc:                     # noqa: BLE001
            raise SystemExit(f'规则文件解析失败 {path.name}: {exc}')
        for rule in data.get('规则', []):
            rules.append(rule)
    if not rules:
        raise SystemExit(f'规则目录为空或没有规则: {rule_dir}')
    return rules


def elastic(word):
    return GAP.join(re.escape(c) for c in word)


def normalize(text):
    return text.translate(ZERO_WIDTH)


def fold_softwrap(text):
    """合并 PDF 硬换行，否则跨行词永远匹配不到。"""
    return re.sub(r'(?<=[\u4e00-\u9fa5，、；：])[ \t]*\n[ \t]*(?=[\u4e00-\u9fa5])', '', text)


# ---------------------------------------------------------------- 匹配
def collect(text, rules):
    hits = []
    for rule in rules:
        if not rule.get('启用'):
            continue
        if rule['层'] == '精确':
            pat = elastic(rule['值']) if rule.get('变体') else re.escape(rule['值'])
            for m in re.finditer(pat, text):
                s0, e0 = m.start(), m.end()
                if rule.get('变体'):
                    while (s0 > 0 and e0 < len(text)
                           and text[s0 - 1] in '（(' and text[e0] in '）)'):
                        s0 -= 1
                        e0 += 1
                hits.append((s0, e0, rule, text[s0:e0]))
        else:
            try:
                regex = re.compile(rule['正则'])
            except re.error:
                continue
            for m in regex.finditer(text):
                if m.groups():
                    s0, e0, val = m.start(1), m.end(1), m.group(1)
                else:
                    s0, e0, val = m.start(), m.end(), m.group(0)
                if not VALIDATORS.get(rule.get('校验', 'none'), lambda v: True)(val):
                    continue
                if rule.get('上下文'):
                    ctx = text[max(0, m.start() - 30):m.start()]
                    if not re.search(rule['上下文'], ctx):
                        continue
                hits.append((s0, e0, rule, val))
    return hits


def resolve(hits):
    """抢占顺序：精确 > 模式 > 语义，再比规则优先级，再比跨度。"""
    hits.sort(key=lambda h: (LAYER_ORDER.get(h[2]['层'], 9),
                             h[2].get('优先级', 999),
                             -(h[1] - h[0])))
    chosen, occ = [], []
    for item in hits:
        s, e = item[0], item[1]
        if any(not (e <= a or s >= b) for a, b in occ):
            continue
        chosen.append(item)
        occ.append((s, e))
    return chosen


def mask(text, rules, name_mode=False, state=None):
    """返回 (脱敏文本, 各类计数, 低置信候选数)

    state 跨文件共享，保证同一实体在整个任务里始终得到同一个占位符。
    """
    if state is None:
        state = {'mapping': {}, 'counters': {}}
    work = normalize(text)
    hits = sorted(resolve(collect(work, rules)), key=lambda h: h[0])

    counts, pending, auto = {}, 0, []
    fmt = '[{}_{}]' if name_mode else '<{}_{}>'
    for s, e, rule, val in hits:
        if rule['层'] == '语义' and not rule.get('自动替换', True):
            pending += 1
            continue
        key = (rule['占位符'], val)
        if key not in state['mapping']:
            state['counters'][rule['占位符']] = state['counters'].get(rule['占位符'], 0) + 1
            state['mapping'][key] = fmt.format(rule['占位符'], state['counters'][rule['占位符']])
        auto.append((s, e, key))
        counts[rule['占位符']] = counts.get(rule['占位符'], 0) + 1

    out = work
    for s, e, key in reversed(auto):
        out = out[:s] + state['mapping'][key] + out[e:]
    return out, counts, pending


def residual(text, rules):
    n = 0
    for rule in rules:
        # 只复核模式层：精确层命中的已替换，语义层本来就不自动替换
        if not rule.get('启用') or rule['层'] != '模式':
            continue
        try:
            regex = re.compile(rule['正则'])
        except re.error:
            continue
        for m in regex.finditer(text):
            val = m.group(1) if m.groups() else m.group(0)
            if VALIDATORS.get(rule.get('校验', 'none'), lambda v: True)(val):
                n += 1
    return n


# ---------------------------------------------------------------- 提取
def extract(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in TEXTIVE:
        for enc in ('utf-8', 'utf-8-sig', 'gb18030'):
            try:
                return path.read_text(encoding=enc)
            except UnicodeDecodeError:
                continue
        return path.read_text(encoding='utf-8', errors='ignore')
    if ext == '.docx':
        if Document is None:
            raise RuntimeError('未安装 python-docx')
        doc = Document(str(path))
        parts = [p.text for p in doc.paragraphs if p.text.strip()]
        for t in doc.tables:
            for row in t.rows:
                cells = [c.text.strip() for c in row.cells if c.text.strip()]
                if cells:
                    parts.append(' | '.join(cells))
        return '\n'.join(parts)
    if ext == '.pptx':
        if Presentation is None:
            raise RuntimeError('未安装 python-pptx')
        prs = Presentation(str(path))
        parts = []
        for idx, slide in enumerate(prs.slides, 1):
            parts.append(f'--- 第 {idx} 页 ---')
            for sh in slide.shapes:
                if getattr(sh, 'has_text_frame', False) and sh.text_frame.text.strip():
                    parts.append(sh.text_frame.text)
                if getattr(sh, 'has_table', False):
                    for row in sh.table.rows:
                        cells = [c.text.strip() for c in row.cells if c.text.strip()]
                        if cells:
                            parts.append(' | '.join(cells))
        return '\n'.join(parts)
    if ext == '.pdf':
        if pymupdf is None:
            raise RuntimeError('未安装 pymupdf，无法读取 PDF')
        doc = pymupdf.open(str(path))
        try:
            return '\n'.join(p.get_text() for p in doc)
        finally:
            doc.close()
    raise RuntimeError(f'不支持的格式 {ext}（可用 python-docx / python-pptx / pymupdf 打开的格式才行）')


def main(argv=None):
    ap = argparse.ArgumentParser(description='文档转文本 + 规则驱动脱敏（只回统计，不回显原文）')
    ap.add_argument('--src', required=True, help='输入目录或单个文件')
    ap.add_argument('--out', default=None, help='输出目录（不给则用 --auto 自动放置）')
    ap.add_argument('--auto', action='store_true',
                    help='自动把输出放到 _scratch/<日期>-<输入名>-处理/脱敏/')
    ap.add_argument('--rules', default=None, help='规则目录（默认 ./规则）')
    ap.add_argument('--force', action='store_true', help='忽略缓存强制重跑')
    ap.add_argument('--dry-run', action='store_true', help='只统计不写文件')
    ap.add_argument('--no-map', action='store_true', help='不输出 原名->脱敏名 对照')
    ap.add_argument('--no-glossary', action='store_true',
                    help='不输出 占位符->原值 对照（默认输出，用于交付前还原人名/单位名）')
    args = ap.parse_args(argv)

    here = Path(__file__).resolve().parent
    rules_dir = Path(args.rules) if args.rules else here / '规则'

    # 词库.csv 改过但没同步时自动补上，省掉一步手工操作
    csv_path = rules_dir / '词库.csv'
    json_path = rules_dir / '10-精确.json'
    if csv_path.is_file() and (not json_path.is_file()
                               or csv_path.stat().st_mtime > json_path.stat().st_mtime):
        import subprocess
        vo = here / 'vocab.py'
        if vo.is_file():
            r = subprocess.run([sys.executable, str(vo), '同步'],
                               capture_output=True, text=True,
                               encoding='utf-8', errors='replace')
            if r.returncode == 0:
                print('词库.csv 有改动，已自动同步')
            else:
                print('词库自动同步失败（继续用旧规则）:')
                print((r.stdout or '')[-400:])

    rules = load_rules(rules_dir)
    src = Path(args.src)
    out = Path(args.out) if args.out else None
    if out is None:
        if not args.auto:
            print('错误：需要 --out 指定输出目录，或加 --auto 自动放置')
            return 2
        import datetime
        today = datetime.date.today().strftime('%Y%m%d')
        base = src.resolve().name if src.is_dir() else src.resolve().stem
        out = here.parent.parent / '_scratch' / f'{today}-{base}-处理' / '脱敏'
        print(f'输出目录（自动）: {out}')
    if not src.exists():
        print(f'错误：输入不存在 {src}')
        return 2
    if not args.dry_run:
        out.mkdir(parents=True, exist_ok=True)

    cache_path = out / '.done.json'
    cache = {}
    if cache_path.is_file() and not args.force:
        try:
            cache = json.loads(cache_path.read_text(encoding='utf-8'))
        except (ValueError, OSError):
            cache = {}

    t0 = time.time()
    stats = {'文件数': 0, '未变跳过': 0, '跳过': [], '字符数': 0,
             '替换': {}, '待确认': 0, '残留命中': 0}
    pairs = []
    state = {'mapping': {}, 'counters': {}}
    files = [src] if src.is_file() else [p for p in sorted(src.rglob('*')) if p.is_file()]

    for path in files:
        key = str(path.relative_to(src if src.is_dir() else src.parent))
        sig = f'{path.stat().st_size}:{int(path.stat().st_mtime)}'
        safe_name, _, _ = mask(path.stem, rules, name_mode=True, state=state)
        target = out / f'{safe_name}.txt'

        if not args.force and cache.get(key) == sig and target.is_file():
            stats['未变跳过'] += 1
            continue
        try:
            raw = extract(path)
        except Exception as exc:                     # noqa: BLE001
            stats['跳过'].append({'文件': key, '原因': str(exc)})
            continue
        if not raw.strip():
            stats['跳过'].append({'文件': key, '原因': '提取不到文本（可能是扫描件，需要 OCR）'})
            continue

        masked, counts, pending = mask(fold_softwrap(raw), rules, state=state)
        stats['文件数'] += 1
        stats['字符数'] += len(raw)
        stats['待确认'] += pending
        stats['残留命中'] += residual(masked, rules)
        for k, v in counts.items():
            stats['替换'][k] = stats['替换'].get(k, 0) + v
        pairs.append((key, target.name))

        if not args.dry_run:
            target.write_text(masked, encoding='utf-8')
            cache[key] = sig

    if not args.dry_run:
        cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding='utf-8')
        (out / '_stats.json').write_text(json.dumps(stats, ensure_ascii=False, indent=1), encoding='utf-8')
        if not args.no_map and pairs:
            body = '\n'.join(f'{a}\t{b}' for a, b in pairs)
            (out / '_map.tsv').write_text('原名\t脱敏名\n' + body, encoding='utf-8')
        if not args.no_glossary and state['mapping']:
            rows = ['占位符\t类型\t原值']
            for (kind, val), ph in sorted(state['mapping'].items(), key=lambda x: x[1]):
                rows.append(f'{ph}\t{kind}\t{val}')
            (out / '_glossary.tsv').write_text('\n'.join(rows), encoding='utf-8')

    print('=== 脱敏完成 ===')
    print(f'处理 {stats["文件数"]} 个，未变跳过 {stats["未变跳过"]}，失败 {len(stats["跳过"])} 个')
    print(f'字符数 {stats["字符数"]:,}   残留命中 {stats["残留命中"]}   低置信待确认 {stats["待确认"]}')
    if stats['替换']:
        print('替换统计:')
        for k, v in sorted(stats['替换'].items(), key=lambda x: -x[1]):
            print(f'  {k}: {v} 处')
    if stats['跳过']:
        print('跳过明细（需要装库或人工转换）:')
        for it in stats['跳过']:
            print(f'  {it["文件"]} —— {it["原因"]}')
    print(f'耗时 {time.time() - t0:.1f}s')
    if not args.dry_run:
        print(f'输出目录: {out}')
        print('提示：_map.tsv 与 _glossary.tsv 含原值，任务结束请删除，不要上传。')
    return 0


if __name__ == '__main__':
    sys.exit(main())

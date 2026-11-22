#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""vocab.py —— 用一张 CSV 管理精确层词表

只做一件事：把 规则/词库.csv 变成 规则/10-精确.json。
你只需要编辑 CSV，别的都自动完成。

用法:
    python vocab.py 同步                  校验 CSV 并生成 10-精确.json（含效果预览）
    python vocab.py 查看 [类别]           列出词库
    python vocab.py 加 <类别> <词> [变体]  往 CSV 末尾追加一条并同步
    python vocab.py 停用 <词>             把某个词改成停用（不删行）
    python vocab.py 预览 <文本>           看这段文本会被替换成什么样
"""

import argparse
import json
import re
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass

HERE = Path(__file__).resolve().parent
CSV_PATH = HERE / '规则' / '词库.csv'
JSON_PATH = HERE / '规则' / '10-精确.json'
COLUMNS = ['类别', '词', '变体', '占位符', '启用', '备注']
GAP = r'[\s（）()\[\]【】·\-—]{0,2}'


def read_csv(path: Path):
    if not path.is_file():
        # 首次使用：从空模板初始化，让发布版开箱可用
        tpl = path.parent / '词库-空模板.csv'
        if tpl.is_file():
            path.write_text(tpl.read_text(encoding='utf-8-sig'), encoding='utf-8-sig')
            print(f'（首次使用，已从空模板创建 {path.name}）')
        else:
            raise SystemExit(f'找不到词库文件: {path}')
    text = None
    for enc in ('utf-8-sig', 'gb18030'):
        try:
            text = path.read_text(encoding=enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise SystemExit('词库编码无法识别，请另存为 UTF-8')

    rows, bad = [], []
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        cells = [c.strip() for c in line.split(',')]
        if lineno == 1 and cells and cells[0] == '类别':
            continue
        if len(cells) < 6:
            cells += [''] * (6 - len(cells))
        rows.append((lineno, dict(zip(COLUMNS, cells[:6]))))
    return rows, bad


def yes(v, default=True):
    v = (v or '').strip().lower()
    if not v:
        return default
    return v in ('是', 'y', 'yes', 'true', '1', '开')


def validate(rows):
    errors, warns, seen = [], [], {}
    clean = []
    for lineno, r in rows:
        tag = f'第 {lineno} 行'
        kind = r['类别'].strip()
        word = r['词'].strip()

        if not kind:
            errors.append(f'{tag}: 类别为空')
            continue
        if not word:
            errors.append(f'{tag}: 词为空')
            continue
        if len(word) < 2:
            warns.append(f'{tag}: 「{word}」只有 1 个字，会被跳过（单字误伤太大）')
            continue
        if ',' in word:
            errors.append(f'{tag}: 词里不能有英文逗号')
            continue

        key = (kind, word)
        if key in seen:
            warns.append(f'{tag}: 「{word}」与第 {seen[key]} 行重复，只保留第一条')
            continue
        seen[key] = lineno

        clean.append({
            '类别': kind,
            '词': word,
            '变体': yes(r['变体'], True),
            '占位符': r['占位符'].strip() or kind,
            '启用': yes(r['启用'], True),
            '备注': r['备注'].strip(),
            '行号': lineno,
        })
    return clean, errors, warns


def build_json(items, version):
    rules = []
    for i, it in enumerate(items, 1):
        rule = {
            'id': f'X-{i:03d}',
            '层': '精确',
            '类别': it['类别'],
            '名称': it['词'],
            '值': it['词'],
            '变体': it['变体'],
            '占位符': it['占位符'],
            '启用': it['启用'],
            '来源': '词库.csv',
            '添加时间': version,
        }
        if it['备注']:
            rule['备注'] = it['备注']
        rules.append(rule)
    return {
        '层': '精确',
        '说明': '由 词库.csv 自动生成，不要手工编辑此文件；改词请改 词库.csv 后跑 vocab.py 同步',
        '版本': version,
        '规则': rules,
    }


def effect_of(rule):
    """把一条规则翻译成一句人话，说明它会产生什么效果。"""
    if not rule['启用']:
        return '已停用，不生效'
    ph = f"<{rule['占位符']}_N>"
    if rule['变体']:
        return f'{ph}（容忍括号/空格断开，如「三峡（滨海）储能」也能中）'
    return f'{ph}（必须一字不差才中）'


def cmd_sync(args):
    rows, _ = read_csv(CSV_PATH)
    items, errors, warns = validate(rows)
    if errors:
        print('=== 校验失败，未生成规则 ===')
        for e in errors:
            print(f'  [错误] {e}')
        return 1

    old = {}
    if JSON_PATH.is_file():
        try:
            data = json.loads(JSON_PATH.read_text(encoding='utf-8-sig'))
            old = {r['值']: r for r in data.get('规则', [])}
        except Exception:                            # noqa: BLE001
            old = {}
    new_words = {r['词'] for r in items}

    version = '2026-11-22'
    payload = build_json(items, version)
    JSON_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding='utf-8')

    added = [w for w in new_words if w not in old]
    removed = [w for w in old if w not in new_words]
    disabled = [r['值'] for r in payload['规则'] if not r['启用']]

    print(f'=== 同步完成 ===')
    print(f'读取 {len(rows)} 行，有效 {len(items)} 条，写入 {JSON_PATH.name}')
    print(f'新增 {len(added)}，移除 {len(removed)}，停用 {len(disabled)}')
    if warns:
        print(f'\n警告 {len(warns)}:')
        for w in warns:
            print(f'  {w}')
    if removed:
        print('\n被移除的词（CSV 里已经没有了）:')
        for w in removed:
            print(f'  {w}')

    print('\n=== 效果预览（每条规则会替换成什么）===')
    for rule in payload['规则']:
        mark = '' if rule['启用'] else '  [停用]'
        print(f"  {rule['值']:<14} -> {effect_of(rule)}{mark}")
    print('\n接着建议跑: python check.py && python evaluate.py')
    return 0


def cmd_list(args):
    rows, _ = read_csv(CSV_PATH)
    items, _, _ = validate(rows)
    if args.类别:
        items = [i for i in items if i['类别'] == args.类别]
    if not items:
        print('没有匹配的词')
        return 0
    print(f'{"类别":<6}{"词":<16}{"变体":<6}{"占位符":<8}{"启用":<6}备注')
    for i in items:
        print(f"{i['类别']:<6}{i['词']:<16}{'是' if i['变体'] else '否':<6}"
              f"{i['占位符']:<8}{'是' if i['启用'] else '否':<6}{i['备注']}")
    print(f'\n共 {len(items)} 条')
    return 0


def cmd_add(args):
    word = args.词.strip()
    if not word:
        print('词不能为空')
        return 2
    rows, _ = read_csv(CSV_PATH)
    items, _, _ = validate(rows)
    if any(i['词'] == word for i in items):
        print(f'「{word}」已经在词库里了')
        return 1
    line = f"{args.类别},{word},{'是' if args.变体 else '否'},{args.类别},是,{args.备注 or ''}"
    text = CSV_PATH.read_text(encoding='utf-8-sig')
    if not text.endswith('\n'):
        text += '\n'
    # 用 utf-8-sig 写回，保留 BOM，否则 Excel 在中文 Windows 上会乱码
    CSV_PATH.write_text(text + line + '\n', encoding='utf-8-sig')
    print(f'已追加：{line}')
    return cmd_sync(args)


def cmd_disable(args):
    word = args.词.strip()
    text = CSV_PATH.read_text(encoding='utf-8-sig')
    lines, hit = text.splitlines(), 0
    out = []
    for line in lines:
        cells = [c.strip() for c in line.split(',')]
        if len(cells) >= 6 and cells[1] == word:
            cells[4] = '否'
            line = ','.join(cells)
            hit += 1
        out.append(line)
    if not hit:
        print(f'没找到「{word}」')
        return 1
    CSV_PATH.write_text('\n'.join(out) + '\n', encoding='utf-8-sig')
    print(f'已停用「{word}」（行保留，可随时改回是）')
    return cmd_sync(args)


def cmd_preview(args):
    rows, _ = read_csv(CSV_PATH)
    items, _, _ = validate(rows)
    text = args.文本
    hits = []
    for i in items:
        if not i['启用']:
            continue
        pat = GAP.join(re.escape(c) for c in i['词']) if i['变体'] else re.escape(i['词'])
        for m in re.finditer(pat, text):
            hits.append((m.start(), m.end(), i))
    hits.sort(key=lambda h: -(h[1] - h[0]))
    chosen, occ = [], []
    for h in hits:
        if any(not (h[1] <= a or h[0] >= b) for a, b in occ):
            continue
        chosen.append(h)
        occ.append((h[0], h[1]))
    chosen.sort(key=lambda h: -h[0])
    out, counter = text, {}
    for s, e, i in chosen:
        counter[i['占位符']] = counter.get(i['占位符'], 0) + 1
        out = out[:s] + f"<{i['占位符']}_{counter[i['占位符']]}>" + out[e:]
    print(f'原文: {text}')
    print(f'脱敏: {out}')
    print(f'命中 {len(chosen)} 处')
    for s, e, i in sorted(chosen):
        print(f"  「{text[s:e]}」 <- {i['类别']} / {i['占位符']}")
    return 0


def menu():
    """无参数启动时的交互菜单（给不熟命令行的人用）"""
    from types import SimpleNamespace
    while True:
        print('\n' + '=' * 40)
        print('  词库管理')
        print('=' * 40)
        print('  1. 同步（改完 CSV 后跑这个）')
        print('  2. 查看全部')
        print('  3. 加一个词')
        print('  4. 预览效果')
        print('  5. 停用一个词')
        print('  0. 退出')
        print('=' * 40)
        try:
            choice = input('请输入数字: ').strip()
        except (EOFError, KeyboardInterrupt):
            break
        if choice == '0':
            break
        if choice == '1':
            cmd_sync(None)
        elif choice == '2':
            kind = input('只看哪个类别（直接回车=全部）: ').strip() or None
            cmd_list(SimpleNamespace(类别=kind))
        elif choice == '3':
            kind = input('类别（组织/场站/公司/人员/项目/设备）: ').strip()
            word = input('词: ').strip()
            ans = input('容忍括号/空格断开吗？(y/n，人名建议 n): ').strip().lower()
            note = input('备注（可空）: ').strip()
            cmd_add(SimpleNamespace(类别=kind, 词=word,
                                   变体=(ans != 'n'), 备注=note))
        elif choice == '4':
            text = input('输入一句话看看效果: ').strip()
            if text:
                cmd_preview(SimpleNamespace(文本=text))
        elif choice == '5':
            word = input('要停用的词: ').strip()
            if word:
                cmd_disable(SimpleNamespace(词=word))
        else:
            print('没看懂，输入 0-5 的数字')


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        menu()
        return 0
    ap = argparse.ArgumentParser(description='用 词库.csv 管理精确层词表')
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('同步', help='校验 CSV 并生成 10-精确.json')
    p = sub.add_parser('查看', help='列出词库')
    p.add_argument('类别', nargs='?', default=None)
    p = sub.add_parser('加', help='追加一个词并同步')
    p.add_argument('类别')
    p.add_argument('词')
    p.add_argument('--变体', dest='变体', action='store_true', default=True)
    p.add_argument('--无变体', dest='变体', action='store_false')
    p.add_argument('--备注', default='')
    p = sub.add_parser('停用', help='把某个词标记为停用')
    p.add_argument('词')
    p = sub.add_parser('预览', help='看一段文本会被替换成什么')
    p.add_argument('文本')
    args = ap.parse_args(argv)

    return {
        '同步': cmd_sync, '查看': cmd_list, '加': cmd_add,
        '停用': cmd_disable, '预览': cmd_preview,
    }[args.cmd](args)


if __name__ == '__main__':
    sys.exit(main())

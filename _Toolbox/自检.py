#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""自检.py — 检查工作区的文档与实际状态是否一致

默认只读，不修改任何文件；加 --fix 才会执行可自动修的项目（目前只有词库同步）。

用法:
    python 自检.py          只检查
    python 自检.py --fix    检查并把能修的修掉

检查项:
    1. INDEX.md 里列的工具，目录和 README 是否存在
    2. HISTORY.md 登记的项目，目录是否存在
    3. 输出结果/ 下的目录，是否都登记进了 HISTORY
    4. AGENTS.md 提到的工具箱文件是否存在
    5. 每个工具的 .py 能否跑 --help
    6. 词库.csv 与 10-精确.json 是否同步
    7. 根目录有没有不该放的文件
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass

HERE = Path(__file__).resolve().parent          # _Toolbox
ROOT = HERE.parent                              # 工作区根
TOOLBOX = HERE

ROOT_ALLOW = {'AGENTS.md', 'README.md', '.gitignore', '.git'}
ROOT_ALLOW_DIRS = {'_scratch', '_Toolbox', '输入资料', '输出结果'}

issues = []


def ok(msg):
    print(f'  OK    {msg}')


def warn(msg, fixable=False):
    issues.append(('WARN', msg, fixable))
    print(f'  WARN  {msg}')


def fail(msg):
    issues.append(('FAIL', msg, False))
    print(f'  FAIL  {msg}')


def read(path: Path) -> str:
    try:
        return path.read_text(encoding='utf-8-sig')
    except OSError:
        return ''


def check_index():
    print('\n[1] 工具索引 ↔ 实际目录')
    text = read(TOOLBOX / 'INDEX.md')
    rows = re.findall(r'^\|\s*([^|]+?)\s*\|[^|]*\|\s*`([^`]+)`\s*\|', text, re.M)
    rows = [(a, b) for a, b in rows if a not in ('工具', '---', ':---')]
    if not rows:
        warn('INDEX.md 里没解析到工具条目')
        return
    for name, rel in rows:
        target = (ROOT / rel.replace('/', '\\')).resolve()
        if not target.is_dir():
            fail(f'INDEX 列了「{name}」，但目录不存在: {rel}')
        elif not (target / 'README.md').is_file():
            warn(f'工具「{name}」缺 README.md')
        else:
            ok(f'{name} -> {rel}')


def check_history():
    print('\n[2] 归档历史 ↔ 实际项目')
    out_dir = ROOT / '输出结果'
    text = read(out_dir / 'HISTORY.md')
    registered = []
    for line in text.splitlines():
        cells = [c.strip() for c in line.split('|')]
        if len(cells) >= 3 and cells[1] and cells[1] not in ('子目录', ':---'):
            registered.append(cells[1])

    existing = [d.name for d in out_dir.iterdir() if d.is_dir()] if out_dir.is_dir() else []

    for name in registered:
        if (out_dir / name).is_dir():
            ok(f'{name} 已登记且在目录里')
        else:
            fail(f'HISTORY 登记了「{name}」，但 输出结果/{name} 不存在')

    for name in existing:
        if name not in registered:
            warn(f'输出结果/{name} 没有登记进 HISTORY.md')


def check_refs():
    print('\n[3] AGENTS.md 引用的文件')
    text = read(ROOT / 'AGENTS.md')
    names = set(re.findall(r'[\w\-]+\.(?:md|py|cmd|csv)', text))
    names = {n for n in names if n not in ('AGENTS.md', 'README.md', 'INDEX.md', 'HISTORY.md')}
    if not names:
        warn('AGENTS.md 里没找到可检查的文件引用')
        return
    for name in sorted(names):
        hits = [p for p in ROOT.rglob(name)
                if '_scratch' not in p.parts and '.git' not in p.parts]
        if hits:
            ok(f'引用 {name}')
        else:
            warn(f'AGENTS.md 提到 {name}，但工作区里找不到（可能改名了）')


def check_help():
    print('\n[4] 工具入口可运行')
    scripts = [p for p in TOOLBOX.rglob('*.py')
               if p.name not in ('自检.py',) and '测试' not in str(p) and '规则' not in str(p)]
    if not scripts:
        warn('没有找到可检查的 .py')
        return
    for script in scripts:
        try:
            r = subprocess.run([sys.executable, str(script), '--help'],
                               capture_output=True, timeout=20)
            if r.returncode == 0:
                ok(f'{script.parent.name}/{script.name} --help')
            else:
                err = (r.stderr.decode('utf-8', 'replace') or '')[:120]
                fail(f'{script.parent.name}/{script.name} --help 失败: {err.strip()}')
        except subprocess.TimeoutExpired:
            fail(f'{script.parent.name}/{script.name} --help 超时')


def check_vocab(fix: bool):
    print('\n[5] 词库同步状态')
    job = TOOLBOX / '敏感脱敏'
    csv = job / '规则' / '词库.csv'
    js = job / '规则' / '10-精确.json'
    if not csv.is_file():
        warn('没找到 词库.csv')
        return
    if not js.is_file():
        warn('没找到 10-精确.json', fixable=True)
        need = True
    else:
        need = csv.stat().st_mtime > js.stat().st_mtime
    if not need:
        ok('词库.csv 与 10-精确.json 同步')
        return
    if fix:
        r = subprocess.run([sys.executable, str(job / 'vocab.py'), '同步'],
                           capture_output=True, timeout=60)
        if r.returncode == 0:
            ok('已自动同步词库')
        else:
            fail('同步失败: ' + (r.stdout or b'').decode('utf-8', 'replace')[:150])
    else:
        warn('词库.csv 有更新但未同步（加 --fix 可自动修）', fixable=True)


def check_root():
    print('\n[6] 根目录整洁度')
    for item in ROOT.iterdir():
        if item.name in ROOT_ALLOW:
            continue
        if item.is_dir():
            if item.name in ROOT_ALLOW_DIRS or (item / 'AGENTS.md').is_file():
                ok(f'{item.name}/（项目目录）')
            else:
                warn(f'根目录有不在白名单里的目录: {item.name}/')
        else:
            warn(f'根目录有不该放的文件: {item.name}')


def main():
    ap = argparse.ArgumentParser(description='工作区一致性自检（默认只读）')
    ap.add_argument('--fix', action='store_true', help='自动修可修项（目前仅词库同步）')
    args = ap.parse_args()

    print('=' * 50)
    print('  工作区自检' + ('（含自动修复）' if args.fix else '（只读）'))
    print('=' * 50)

    check_index()
    check_history()
    check_refs()
    check_help()
    check_vocab(args.fix)
    check_root()

    fails = [i for i in issues if i[0] == 'FAIL']
    warns = [i for i in issues if i[0] == 'WARN']
    print('\n' + '=' * 50)
    print(f'  结果：{len(fails)} 个错误，{len(warns)} 个警告')
    if warns:
        print('  警告不影响使用，但建议顺手处理')
    print('=' * 50)
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())

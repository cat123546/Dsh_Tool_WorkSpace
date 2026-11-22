#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""备份.py — 把"发布端自留、没有版本控制"的文件打包成 zip

这些文件不在 git 仓库里（SPEC、手册、真实词库、数据），改坏了没有回滚，
所以单独做一个带日期的快照。

用法:
    python backup.py              备份到工作区外的默认目录
    python backup.py --out DIR    指定备份目录
    python backup.py --list       只看会备份哪些，不执行
"""

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass

HERE = Path(__file__).resolve().parent          # _Toolbox
ROOT = HERE.parent                              # 工作区根

# 自留文件（不在 git 里，需要单独备份）
TARGETS = [
    'SPEC.md',
    '使用手册.md',
    '_Toolbox/敏感脱敏/规则/词库.csv',
    '_Toolbox/敏感脱敏/规则/10-精确.json',
    '_Toolbox/敏感脱敏/变更日志.md',
    '输入资料',
    '输出结果',
]

# 明确不备份的
SKIP = ['输入资料/敏感', '输入资料/_归档']


def main():
    ap = argparse.ArgumentParser(description='备份自留文件（不在 git 里的那些）')
    ap.add_argument('--out', default=None, help='备份输出目录，默认在工作区外')
    ap.add_argument('--list', action='store_true', help='只列出会备份的内容')
    args = ap.parse_args()

    print('=' * 50)
    print('  自留文件备份')
    print('=' * 50)

    items = []
    for rel in TARGETS:
        p = ROOT / rel
        if not p.exists():
            print(f'  跳过（不存在）: {rel}')
            continue
        if p.is_dir():
            files = [f for f in p.rglob('*') if f.is_file()]
            size = sum(f.stat().st_size for f in files)
            items.append((p, rel))
            print(f'  {rel}/  ({len(files)} 个文件, {size/1048576:.1f} MB)')
        else:
            items.append((p, rel))
            print(f'  {rel}  ({p.stat().st_size/1024:.1f} KB)')

    if not items:
        print('\n没有可备份的内容')
        return 1

    if args.list:
        print('\n（--list 模式，未实际备份）')
        return 0

    out_dir = Path(args.out) if args.out else ROOT.parent / 'DSH_WorkSpace-自留备份'
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d-%H%M')
    base = out_dir / f'自留备份-{stamp}'

    print(f'\n正在打包到: {base}.zip')
    tmp = out_dir / f'_tmp-{stamp}'
    tmp.mkdir(parents=True, exist_ok=True)
    try:
        for src, rel in items:
            dest = tmp / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            if src.is_dir():
                shutil.copytree(src, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dest)
        archive = shutil.make_archive(str(base), 'zip', str(tmp))
        size = Path(archive).stat().st_size / 1048576
        print(f'完成: {archive}  ({size:.1f} MB)')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # 只保留最近 10 个备份
    olds = sorted(out_dir.glob('自留备份-*.zip'))
    if len(olds) > 10:
        for old in olds[:-10]:
            old.unlink()
            print(f'  清理旧备份: {old.name}')
    print(f'\n备份目录: {out_dir}')
    print(f'当前共有 {len(list(out_dir.glob("自留备份-*.zip")))} 个备份')
    return 0


if __name__ == '__main__':
    sys.exit(main())

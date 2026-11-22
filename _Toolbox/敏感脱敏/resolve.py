#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""resolve.py —— 用 _glossary.tsv 把交付稿里的占位符还原成人能看懂的原值

只做精确匹配。模型改写过的占位符（例如把 <场站_1> 写成「该场站」）不会被猜着还原，
会被列为「无法解析」，这是刻意的：猜就会错，错就会误导。

用法:
    python resolve.py --glossary <_glossary.tsv> --list
    python resolve.py --glossary <_glossary.tsv> --text <文件>
    python resolve.py --glossary <_glossary.tsv> --text <文件> --apply [--out <文件>]

注意: 输出含原值，只给本地看，不要上传。
"""

import argparse
import re
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass

PLACEHOLDER = re.compile(r'[<\[［]([^<>\[\]［］_\s]{1,12})_(\d{1,4})[>\]]')


def load_glossary(path: Path):
    table = {}
    for i, line in enumerate(path.read_text(encoding='utf-8-sig').splitlines()):
        if i == 0 and '占位符' in line:
            continue
        parts = line.split('\t')
        if len(parts) < 3:
            continue
        ph, kind, value = parts[0].strip(), parts[1].strip(), parts[2]
        if ph:
            table[ph] = (kind, value)
    return table


def main(argv=None):
    ap = argparse.ArgumentParser(description='占位符 -> 原值 对照与还原')
    ap.add_argument('--glossary', required=True, help='_glossary.tsv 路径')
    ap.add_argument('--text', help='要检查的文本文件')
    ap.add_argument('--apply', action='store_true', help='把可解析占位符替换成原值')
    ap.add_argument('--out', help='替换结果写到该文件（默认打印到屏幕）')
    ap.add_argument('--list', action='store_true', help='列出全部对照')
    args = ap.parse_args(argv)

    gpath = Path(args.glossary)
    if not gpath.is_file():
        print(f'找不到对照表: {gpath}')
        return 2
    table = load_glossary(gpath)

    if args.list or not args.text:
        print(f'=== 对照表（{len(table)} 条，含原值，勿上传）===')
        for ph, (kind, value) in sorted(table.items()):
            print(f'  {ph:<16} {kind:<8} {value}')
        return 0

    tpath = Path(args.text)
    if not tpath.is_file():
        print(f'找不到文本: {tpath}')
        return 2
    text = tpath.read_text(encoding='utf-8', errors='ignore')

    found = PLACEHOLDER.findall(text)
    seen, resolved, orphan = {}, [], []
    for kind_token, num in found:
        ph = None
        for candidate in (f'<{kind_token}_{num}>', f'[{kind_token}_{num}]'):
            if candidate in table:
                ph = candidate
                break
        raw = f'<{kind_token}_{num}>'
        if ph:
            seen[ph] = seen.get(ph, 0) + 1
            resolved.append(ph)
        else:
            orphan.append(raw)

    total = len(found)
    print('=== 还原检查 ===')
    print(f'文本中占位符出现: {total} 次，去重 {len(set(resolved) | set(orphan))} 个')
    print(f'可解析: {total - len(orphan)} 次   无法解析: {len(orphan)} 次')

    if seen:
        print('\n可解析明细:')
        for ph, cnt in sorted(seen.items()):
            kind, value = table[ph]
            print(f'  {ph} × {cnt}  ->  {value}')

    if orphan:
        print('\n无法解析（模型改写或编造，需人工判断）:')
        for ph in sorted(set(orphan)):
            print(f'  {ph}')

    if args.apply:
        def resolve_one(m):
            token = m.group(0)
            for candidate in (token,
                              token.replace('<', '[').replace('>', ']'),
                              token.replace('[', '<').replace(']', '>')):
                if candidate in table:
                    return table[candidate][1]
            return token

        out = PLACEHOLDER.sub(resolve_one, text)
        if args.out:
            Path(args.out).write_text(out, encoding='utf-8')
            print(f'\n已写入: {args.out}（含原值）')
        else:
            print('\n=== 还原结果（含原值）===')
            print(out)
    return 0


if __name__ == '__main__':
    sys.exit(main())

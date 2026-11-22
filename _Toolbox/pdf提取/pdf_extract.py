#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pdf_extract.py — PDF 页面体检 / 全文提取 / 指定页提图

用法:
    python pdf_extract.py survey --pdf 某文件.pdf
    python pdf_extract.py text   --pdf 某文件.pdf --out 输出目录 [--name 全文.txt]
    python pdf_extract.py images --pdf 某文件.pdf --pages 4,5,8 --out 输出目录 [选项]

选项:
    --clip-top N   从页面顶部裁掉 N 磅（常用于去掉 PPT 标题栏），默认 0
    --dpi N        出图分辨率，默认 190
    --prefix STR   图片文件名前缀，默认 p（生成 p04.png 这样）

依赖: pymupdf  (pip install pymupdf)
"""

import argparse
import os
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass

try:
    import pymupdf
except ImportError:
    print('缺少依赖：请先安装 pymupdf  （pip install pymupdf）')
    sys.exit(1)


def open_pdf(path: str):
    if not os.path.isfile(path):
        raise SystemExit(f'找不到文件：{path}')
    return pymupdf.open(path)


def cmd_survey(args):
    """逐页统计字符数与图片数，用来判断是文字型还是扫描件。"""
    doc = open_pdf(args.pdf)
    size_mb = os.path.getsize(args.pdf) / 1048576
    print(f'文件: {args.pdf}')
    print(f'页数: {doc.page_count}   大小: {size_mb:.2f} MB')
    print(f'{"页":>4}{"字符":>8}{"图片":>6}{"最大边":>8}')

    low, total_chars, imaged = [], 0, 0
    for i, page in enumerate(doc, 1):
        text = page.get_text('text')
        chars = len(text)
        images = page.get_images(full=True)
        biggest = 0
        for im in images:
            try:
                info = doc.extract_image(im[0])
                biggest = max(biggest, max(info['width'], info['height']))
            except Exception:                        # noqa: BLE001
                pass
        total_chars += chars
        if images:
            imaged += 1
        if chars < 60 and images:
            low.append(i)
        print(f'{i:>4}{chars:>8}{len(images):>6}{biggest:>8}')

    page_count = doc.page_count
    doc.close()
    print()
    print(f'总字符数: {total_chars:,}')
    print(f'有图的页: {imaged} / {page_count}')
    print(f'疑似扫描页（字符<60 且有图）: {low if low else "无"}')
    if total_chars < 200 and page_count > 0:
        print('判定: 基本是扫描件，纯文本提取没用，需要 OCR')
    elif low:
        print(f'判定: 文字型，但 {len(low)} 页靠图，这些页要单独处理')
    else:
        print('判定: 文字型，可直接用 text 子命令提取')
    return 0


def cmd_text(args):
    """提取全文，按页分隔写出。"""
    doc = open_pdf(args.pdf)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    parts = []
    for i, page in enumerate(doc, 1):
        parts.append(f'\n========== PAGE {i} ==========\n')
        parts.append(page.get_text('text'))
    doc.close()

    target = out / (args.name or '全文.txt')
    content = ''.join(parts)
    target.write_text(content, encoding='utf-8')
    print(f'已写出: {target}')
    print(f'字符数: {len(content):,}')
    return 0


def parse_pages(spec: str):
    pages = []
    for chunk in spec.split(','):
        chunk = chunk.strip()
        if not chunk:
            continue
        if '-' in chunk:
            a, b = chunk.split('-', 1)
            pages.extend(range(int(a), int(b) + 1))
        else:
            pages.append(int(chunk))
    return sorted(set(pages))


def cmd_images(args):
    """把指定页渲染成 PNG，可裁掉顶部标题栏。"""
    pages = parse_pages(args.pages)
    if not pages:
        print('没有指定页码')
        return 2

    doc = open_pdf(args.pdf)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    done = 0
    for pno in pages:
        if pno < 1 or pno > doc.page_count:
            print(f'  跳过第 {pno} 页：超出范围（共 {doc.page_count} 页）')
            continue
        page = doc[pno - 1]
        rect = page.rect
        if args.clip_top:
            clip = pymupdf.Rect(rect.x0, rect.y0 + args.clip_top, rect.x1, rect.y1)
        else:
            clip = rect
        pix = page.get_pixmap(clip=clip, dpi=args.dpi)
        path = out / f'{args.prefix}{pno:02d}.png'
        pix.save(str(path))
        print(f'  p{pno:02d} -> {path.name}  {pix.width}x{pix.height}')
        done += 1

    doc.close()
    print(f'完成：{done} 张，输出目录 {out}')
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description='PDF 页面体检 / 全文提取 / 指定页提图')
    sub = ap.add_subparsers(dest='cmd', required=True)

    p = sub.add_parser('survey', help='逐页统计字符与图片，判断文字型还是扫描件')
    p.add_argument('--pdf', required=True)
    p.set_defaults(func=cmd_survey)

    p = sub.add_parser('text', help='提取全文')
    p.add_argument('--pdf', required=True)
    p.add_argument('--out', required=True, help='输出目录')
    p.add_argument('--name', default=None, help='输出文件名，默认 全文.txt')
    p.set_defaults(func=cmd_text)

    p = sub.add_parser('images', help='按页提图')
    p.add_argument('--pdf', required=True)
    p.add_argument('--pages', required=True, help='页码，如 4,5,8 或 3-7')
    p.add_argument('--out', required=True, help='输出目录')
    p.add_argument('--clip-top', dest='clip_top', type=float, default=0,
                   help='从页面顶部裁掉多少磅（去掉标题栏），默认 0')
    p.add_argument('--dpi', type=int, default=190)
    p.add_argument('--prefix', default='p', help='文件名前缀，默认 p')
    p.set_defaults(func=cmd_images)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())

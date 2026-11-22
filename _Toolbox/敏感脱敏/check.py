# -*- coding: utf-8 -*-
"""规则集校验：格式、字段完整性、正则可编译、校验器名合法、id 唯一、id 与层前缀一致"""
import json
import re
import sys
from pathlib import Path

for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass

HERE = Path(__file__).resolve().parent
LAYER_NEED = {
    '精确': ['id', '层', '类别', '名称', '值', '占位符', '启用'],
    '模式': ['id', '层', '类别', '名称', '正则', '占位符', '启用', '置信度'],
    '语义': ['id', '层', '类别', '名称', '正则', '占位符', '启用', '置信度'],
}
PREFIX = {'精确': 'X', '模式': 'P', '语义': 'S'}
VALIDATORS = {'none', 'id18', 'uscc', 'luhn'}


def main():
    import argparse
    ap = argparse.ArgumentParser(description='规则集格式校验：格式、字段、正则、id 唯一性')
    ap.add_argument('path', nargs='?', default=None, help='规则文件或目录，默认 ./规则')
    ap.add_argument('--help-note', action='store_true', help=argparse.SUPPRESS)
    args, _ = ap.parse_known_args()
    target = Path(args.path) if args.path else HERE / '规则'
    paths = sorted(target.glob('*.json')) if target.is_dir() else [target]
    errors, warns, rules = [], [], []
    for p in paths:
        try:
            data = json.loads(p.read_text(encoding='utf-8-sig'))
        except Exception as exc:                      # noqa: BLE001
            print(f'{p.name} 解析失败: {exc}')
            return 1
        got = data.get('规则')
        if not isinstance(got, list):
            print(f'{p.name} 缺少 规则 数组')
            return 1
        rules.extend(got)
    if not rules:
        print('没有找到任何规则')
        return 1

    seen = {}
    for r in rules:
        rid, layer = r.get('id'), r.get('层')
        if not rid:
            errors.append('存在缺少 id 的规则')
            continue
        if rid in seen:
            errors.append(f'{rid}: id 重复')
        seen[rid] = layer

        need = LAYER_NEED.get(layer)
        if need is None:
            errors.append(f'{rid}: 未知层级 {layer!r}')
            continue
        for f in need:
            if f not in r:
                errors.append(f'{rid}: 缺少字段 {f}')

        if not str(rid).startswith(PREFIX[layer]):
            errors.append(f'{rid}: id 前缀与层级 {layer} 不一致')

        if layer in ('模式', '语义'):
            try:
                re.compile(r['正则'])
            except re.error as exc:
                errors.append(f'{rid}: 正则无法编译 —— {exc}')
            if r.get('校验') not in VALIDATORS:
                errors.append(f'{rid}: 校验器 {r.get("校验")!r} 不在 {sorted(VALIDATORS)}')
            if layer == '语义' and '自动替换' not in r:
                warns.append(f'{rid}: 语义层未声明 自动替换，默认按 True 处理')

        if layer == '精确' and len(str(r.get('值', ''))) < 2:
            errors.append(f'{rid}: 精确层词少于 2 字，误伤风险高')

    print(f'规则文件: {len(paths)} 个（{target}）')
    print(f'规则总数: {len(rules)}   '
          f'精确 {sum(1 for r in rules if r.get("层") == "精确")} / '
          f'模式 {sum(1 for r in rules if r.get("层") == "模式")} / '
          f'语义 {sum(1 for r in rules if r.get("层") == "语义")}')
    print(f'禁用规则: {sum(1 for r in rules if not r.get("启用"))}')
    if warns:
        print(f'\n警告 {len(warns)}:')
        for w in warns:
            print(f'  - {w}')
    if errors:
        print(f'\n错误 {len(errors)}:')
        for e in errors:
            print(f'  - {e}')
        return 1
    print('\n校验通过：无格式错误')
    return 0


if __name__ == '__main__':
    sys.exit(main())

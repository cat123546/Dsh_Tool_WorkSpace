# -*- coding: utf-8 -*-
"""评测：按类别统计召回率与误报率（只输出指标，不输出原文）"""
import calendar
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
GAP = r'[\s（）()\[\]【】·\-—]{0,2}'


def canon(s):
    return re.sub(GAP, '', s)


def elastic(word):
    return GAP.join(re.escape(c) for c in word)


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


VALIDATORS = {'id18': id18_valid, 'uscc': uscc_valid, 'luhn': luhn_valid, 'none': lambda v: True}


def run_rules(text, rules):
    hits = []
    for rule in rules:
        if not rule.get('启用'):
            continue
        if rule['层'] == '精确':
            pat = elastic(rule['值']) if rule.get('变体') else re.escape(rule['值'])
            for m in re.finditer(pat, text):
                s0, e0 = m.start(), m.end()
                # 变体匹配时，若两侧紧邻成对括号，一并纳入，避免替换后留下孤立括号
                if rule.get('变体'):
                    while (s0 > 0 and e0 < len(text)
                           and text[s0 - 1] in '（(' and text[e0] in '）)'):
                        s0 -= 1
                        e0 += 1
                hits.append((s0, e0, rule, text[s0:e0]))
        else:
            for m in re.finditer(rule['正则'], text):
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

    LO = {'精确': 0, '模式': 1, '语义': 2}
    hits.sort(key=lambda h: (LO.get(h[2]['层'], 9), h[2].get('优先级', 999), -(h[1] - h[0])))
    chosen, occ = [], []
    for item in hits:
        s, e = item[0], item[1]
        if any(not (e <= a or s >= b) for a, b in occ):
            continue
        chosen.append(item)
        occ.append((s, e))
    return chosen


def test_priority(rules):
    """同一段文本里三层规则共存，验证抢占顺序 精确 > 模式 > 语义。"""
    text = ('负责人：宋阳，电话 13800138000，'
            '主送单位：长江电力、三峡建工，坐标 30.5231, 114.3123')
    chosen = run_rules(text, rules)
    auto = [(r['占位符'], v) for _, _, r, v in chosen
            if not (r['层'] == '语义' and not r.get('自动替换', True))]
    kinds = [k for k, _ in auto]
    checks = [
        ('精确层·人员(宋阳) 命中', '人员' in kinds),
        ('精确层·组织 命中 >= 2', kinds.count('组织') >= 2),
        ('模式层·手机号 命中', '手机号' in kinds),
        ('模式层·坐标 命中', '坐标' in kinds),
        ('语义层未抢占精确层区间', '单位列表' not in kinds),
    ]
    print('\n=== 层级优先级测试 ===')
    ok = True
    for label, passed in checks:
        print(f'  {"PASS" if passed else "FAIL"}  {label}')
        ok = ok and passed
    print(f'  结果: {"通过" if ok else "失败"}')
    return ok


def main():
    rules = []
    for _p in sorted((HERE / '规则').glob('*.json')):
        rules.extend(json.loads(_p.read_text(encoding='utf-8-sig'))['规则'])
    samples = json.loads((HERE / '标注集.json').read_text(encoding='utf-8'))['样本']

    stat = {}
    pending = 0
    for smp in samples:
        text = smp['文本']
        chosen = run_rules(text, rules)

        got, pend = [], []
        for _, _, r, v in chosen:
            if r['层'] == '语义' and not r.get('自动替换', True):
                pend.append((r['占位符'], v))
            else:
                got.append((r['占位符'], v))
        pending += len(pend)

        expected = list(smp['应命中'])
        used = [False] * len(got)
        for etype, eval_ in expected:
            hit = False
            for i, (gtype, gval) in enumerate(got):
                if used[i] or gtype != etype:
                    continue
                ce, cg = canon(eval_), canon(gval)
                if ce == cg or ce in cg or cg in ce:
                    used[i] = True
                    hit = True
                    break
            row = stat.setdefault(etype, {'TP': 0, 'FN': 0, 'FP': 0})
            if hit:
                row['TP'] += 1
            else:
                row['FN'] += 1
        for i, (gtype, gval) in enumerate(got):
            if not used[i]:
                stat.setdefault(gtype, {'TP': 0, 'FN': 0, 'FP': 0})['FP'] += 1

    print('=== 按类型：召回率 / 误报率 ===')
    print(f'{"类型":<10}{"TP":>4}{"FN":>4}{"FP":>4}{"召回":>9}{"精确率":>9}')
    tot = {'TP': 0, 'FN': 0, 'FP': 0}
    for k in sorted(stat):
        v = stat[k]
        tp, fn, fp = v['TP'], v['FN'], v['FP']
        rec = tp / (tp + fn) if tp + fn else 1.0
        prec = tp / (tp + fp) if tp + fp else 1.0
        print(f'{k:<10}{tp:>4}{fn:>4}{fp:>4}{rec:>8.0%}{prec:>9.0%}')
        for key in tot:
            tot[key] += v[key]
    rec = tot['TP'] / (tot['TP'] + tot['FN']) if tot['TP'] + tot['FN'] else 0
    prec = tot['TP'] / (tot['TP'] + tot['FP']) if tot['TP'] + tot['FP'] else 0
    print(f'{"合计":<10}{tot["TP"]:>4}{tot["FN"]:>4}{tot["FP"]:>4}{rec:>8.0%}{prec:>9.0%}')
    print(f'\n语义层低置信候选(待确认, 未计入): {pending}')
    print(f'样本数: {len(samples)}')

    print('\n=== 漏报明细（类型 / 样本号）===')
    for smp in samples:
        chosen = run_rules(smp['文本'], rules)
        got = [(r['占位符'], v) for _, _, r, v in chosen if not (r['层'] == '语义' and not r.get('自动替换', True))]
        for etype, eval_ in smp['应命中']:
            ok = any(gtype == etype and (canon(eval_) == canon(gval) or canon(eval_) in canon(gval) or canon(gval) in canon(eval_))
                     for gtype, gval in got)
            if not ok:
                print(f'  {smp["id"]}  期望[{etype}]  未命中')

    test_priority(rules)


if __name__ == '__main__':
    main()

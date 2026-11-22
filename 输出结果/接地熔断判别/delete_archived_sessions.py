# -*- coding: utf-8 -*-
"""删除两个已归档会话：会话日志 + 投影缓存 + workspace.json 索引引用。
操作前自动备份 workspace.json。"""
import json
import os
import shutil
import time

HOME = r"C:\Users\CAT\.dsh"
WS_DIR = os.path.join(HOME, "sessions", "--D-DSH_WorkSpace--")
PC_DIR = os.path.join(HOME, "storages", "session_projcache", "sessions")
WS_JSON = os.path.join(HOME, "storages", "workspace.json")

TARGETS = [
    "session-cf5ddee4-8dae-48a4-9482-94219a3f96f2",
    "session-4feb8eda-3d8b-4d5b-815b-795d3a903cf9",
]

print("=" * 60)
print("步骤 1：备份 workspace.json")
stamp = time.strftime("%Y%m%d-%H%M%S")
bak = f"{WS_JSON}.bak-{stamp}"
shutil.copy2(WS_JSON, bak)
print("  备份 ->", bak)

print("=" * 60)
print("步骤 2：删除会话日志目录")
for sid in TARGETS:
    d = os.path.join(WS_DIR, sid)
    if os.path.isdir(d):
        size = sum(
            os.path.getsize(os.path.join(dp, f))
            for dp, _, fs in os.walk(d)
            for f in fs
        )
        shutil.rmtree(d)
        print(f"  已删目录 {sid}  ({round(size/1024,1)} KB)")
    else:
        print(f"  跳过（不存在）{sid}")

print("=" * 60)
print("步骤 3：删除投影缓存")
for sid in TARGETS:
    p = os.path.join(PC_DIR, sid + ".json")
    if os.path.isfile(p):
        size = os.path.getsize(p)
        os.remove(p)
        print(f"  已删缓存 {sid}.json  ({round(size/1024,1)} KB)")
    else:
        print(f"  跳过（不存在）{sid}.json")

print("=" * 60)
print("步骤 4：从 workspace.json 移除引用")
with open(WS_JSON, encoding="utf-8") as f:
    data = json.load(f)

g = data.get("global", {})
before_arch = list(g.get("archivedSessionIds", []))
g["archivedSessionIds"] = [s for s in before_arch if s not in TARGETS]
g["pinnedSessionIds"] = [s for s in g.get("pinnedSessionIds", []) if s not in TARGETS]

removed_ws = 0
for ws in data.get("tables", {}).get("workspaces", {}).values():
    ids = ws.get("sessionIds", [])
    kept = [s for s in ids if s not in TARGETS]
    removed_ws += len(ids) - len(kept)
    ws["sessionIds"] = kept

with open(WS_JSON, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"  archivedSessionIds: {before_arch} -> {g['archivedSessionIds']}")
print(f"  从工作区 sessionIds 中移除 {removed_ws} 条")

print("=" * 60)
print("步骤 5：校验")
with open(WS_JSON, encoding="utf-8") as f:
    chk = json.load(f)
left_arch = chk["global"]["archivedSessionIds"]
left_ws = [s for ws in chk["tables"]["workspaces"].values() for s in ws["sessionIds"]]
print("  剩余 archivedSessionIds:", left_arch)
print("  残留引用:", [s for s in TARGETS if s in left_arch or s in left_ws] or "无")

for sid in TARGETS:
    print(f"  {sid}: dir={os.path.isdir(os.path.join(WS_DIR, sid))}, cache={os.path.isfile(os.path.join(PC_DIR, sid + '.json'))}")

print("=" * 60)
print("完成")

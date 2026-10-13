# -*- coding: utf-8 -*-
"""raw/raw-s2.json -> candidates-s2.md (utf-8, 紧凑)"""
import json, os
HERE = os.path.dirname(os.path.abspath(__file__))
d = json.load(open(os.path.join(HERE, "raw", "raw-s2.json"), encoding="utf-8"))
out = []
for label, items in d.items():
    if isinstance(items, dict):
        out.append(f"\n== {label} == ERROR {items.get('error')}")
        continue
    out.append(f"\n== {label} ({len(items)}) ==")
    for r in sorted(items, key=lambda x: (str(x.get('year') or ''), x.get('citations') or 0), reverse=True):
        out.append(f"  {r['year']} [{r['citations']}] {r.get('venue') or ''} | {r['title']} | {r.get('doi') or r.get('arxiv') or ''}")
open(os.path.join(HERE, "candidates-s2.md"), "w", encoding="utf-8").write("\n".join(out))
print("ok", sum(len(v) for v in d.values() if isinstance(v, list)))

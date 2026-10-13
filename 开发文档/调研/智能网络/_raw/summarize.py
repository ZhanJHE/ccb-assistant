# -*- coding: utf-8 -*-
"""过滤 + 去重 raw/*.json -> candidates.md (utf-8)。"""
import json, os, glob

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")

NET = ["network", "networking", "routing", "route", "traffic", "packet", "congestion", "tcp",
       "flow", "intrusion", "anomaly", "ddos", "switch", "protocol", "telemetry", "sdn",
       "datacenter", "data center", "wifi", "wi-fi", "wireless", "5g", "6g", "ran", "qos",
       "bandwidth", "latency", "in-network", "aiops", "root cause", "root-cause", "fault",
       "topology", "llm", "agent", "load balanc", "schedul", "resource alloc", "network management"]
OFF = ["vehicle routing", "capacitated", "cerebral", "coal", "isogeometric", "finite element",
       "protein", "molecular", "knee joint", "shuttle car", "public transport", "entanglement",
       "auditory", "hemodynamic", "official statistics", "learning curve", "biology", "clinical",
       "fraud", "corruption", "finite element", "property graph", "travel time", "last-mile",
       "logistics", "isac drone", "mmwave", "channel reconstruction", "geospatial", "sensing"]

def ok(t):
    if not t:
        return False
    tl = t.lower()
    if any(k in tl for k in OFF):
        return False
    return any(k in tl for k in NET)

seen = set()
out = []
for f in sorted(glob.glob(os.path.join(RAW, "*.json"))):
    src = os.path.basename(f).replace("raw-", "").replace(".json", "")
    d = json.load(open(f, encoding="utf-8"))
    out.append(f"\n\n########## SOURCE: {src} ##########")
    for label, items in d.items():
        if isinstance(items, dict):
            continue
        rows = []
        for r in items:
            t = (r.get("title") or "").strip()
            key = t.lower()[:70]
            if not ok(t):
                continue
            if key in seen:
                continue
            seen.add(key)
            rows.append(r)
        out.append(f"\n== {label} ({len(rows)}/{len(items)}) ==")
        for r in sorted(rows, key=lambda x: str(x.get("year") or ""), reverse=True):
            y = r.get("year") or "?"
            c = r.get("citations")
            ven = (r.get("venue") or "").strip()
            rid = r.get("id") or ""
            tt = (r.get("title") or "").strip()
            cc = f"[{c}]" if c is not None else ""
            ev = f" | {ven}" if ven else ""
            out.append(f"  {y} {cc}{ev} | {tt} | {rid}")

open(os.path.join(HERE, "candidates.md"), "w", encoding="utf-8").write("\n".join(out))
print(f"written candidates.md, {len(seen)} unique relevant records")

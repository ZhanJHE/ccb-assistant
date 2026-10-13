# -*- coding: utf-8 -*-
"""为 AIN 43 条补齐 一作/标题（S2 paper/batch），输出 _raw/authors.json。"""
import os, json, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
KEY = os.environ.get("S2_API_KEY", "")
ver = json.load(open(os.path.join(HERE, "raw", "verified.json"), encoding="utf-8"))

EXTRA = [
 ("AIN-38", "2605.09260"), ("AIN-39", "2502.12834"), ("AIN-40", "2608.23179"),
 ("AIN-41", "2512.16381"), ("AIN-42", "2601.06640"), ("AIN-43", "2609.12170"),
]

ids, meta = [], {}
for e in ver:
    i = ("DOI:" + e["doi"]) if e["doi"] else ("ARXIV:" + e["arxiv"])
    ids.append(i); meta[i] = e["num"]
for num, ax in EXTRA:
    i = "ARXIV:" + ax
    ids.append(i); meta[i] = num

url = "https://api.semanticscholar.org/graph/v1/paper/batch?fields=title,year,venue,authors,citationCount,externalIds"
body = json.dumps({"ids": ids}).encode()
res = None
for attempt in range(4):
    try:
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json", "x-api-key": KEY})
        with urllib.request.urlopen(req, timeout=90) as r:
            res = json.loads(r.read().decode("utf-8", "replace"))
        break
    except Exception as ex:
        print("retry", attempt, ex); time.sleep(3 * (attempt + 1))

out = {}
if res:
    for i, p in zip(ids, res):
        num = meta[i]
        if not p:
            out[num] = {"author": "待补", "title": None}
            continue
        au = p.get("authors") or []
        first = au[0]["name"] if au else "待补"
        out[num] = {"author": first, "title": p.get("title"), "year": p.get("year"), "venue": p.get("venue"), "citations": p.get("citationCount")}
        print(f"{num} | {first} | {p.get('year')} | {p.get('venue')}")
json.dump(out, open(os.path.join(HERE, "raw", "authors.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("missing:", [k for k, v in out.items() if v.get("author") in (None, "待补")])

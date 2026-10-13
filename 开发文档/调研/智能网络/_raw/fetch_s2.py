# -*- coding: utf-8 -*-
"""Semantic Scholar 检索器（AIN 子方向 IV）。1 RPS。
用法: python fetch_s2.py
输出: _raw/raw-s2.json + stdout 紧凑清单。"""
import os, json, time, urllib.request, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
KEY = os.environ.get("S2_API_KEY", "")
BASE = "https://api.semanticscholar.org/graph/v1/paper/search"
FIELDS = "title,year,venue,citationCount,externalIds,authors"

QUERIES = [
    ("in-net-ml", "in-network machine learning switch data plane"),
    ("cls", "encrypted traffic classification deep learning"),
    ("pred", "network traffic prediction deep learning"),
    ("ids", "network intrusion detection deep learning"),
    ("anom", "network anomaly detection machine learning"),
    ("cc", "learning-based congestion control"),
    ("cc-rl", "reinforcement learning congestion control datacenter"),
    ("llm-net", "large language model network management"),
    ("netagent", "LLM agent network automation troubleshooting"),
    ("aiops", "AIOps root cause analysis"),
    ("te-rl", "deep reinforcement learning traffic engineering"),
    ("gnn-net", "graph neural network for networking"),
    ("survey", "machine learning for networking survey"),
    ("dt", "network digital twin"),
    ("prog-ml", "programmable switch machine learning inference"),
    ("ibn", "intent-based networking large language model"),
]

def get(url):
    req = urllib.request.Request(url, headers={"x-api-key": KEY, "User-Agent": "AIN-Research/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8", "replace"))

def main():
    out = {}
    for label, q in QUERIES:
        url = BASE + "?query=" + urllib.parse.quote(q) + "&limit=15&fields=" + FIELDS
        for attempt in range(4):
            try:
                d = get(url)
                items = []
                for p in d.get("data", []):
                    ex = p.get("externalIds") or {}
                    items.append({
                        "title": p.get("title"),
                        "year": p.get("year"),
                        "venue": p.get("venue"),
                        "citations": p.get("citationCount"),
                        "doi": ex.get("DOI"),
                        "arxiv": ex.get("ArXiv"),
                        "url": ("https://doi.org/" + ex["DOI"]) if ex.get("DOI") else
                               ("https://arxiv.org/abs/" + ex["ArXiv"]) if ex.get("ArXiv") else None,
                    })
                out[label] = items
                print(f"[S2:{label}] {len(items)} hits ({q})")
                break
            except Exception as ex:
                msg = str(ex)
                if "429" in msg and attempt < 3:
                    time.sleep(2 ** attempt + 2)
                    continue
                out[label] = {"error": msg}
                print(f"[S2:{label}] ERROR {msg}")
                break
        time.sleep(1.2)
    os.makedirs(os.path.join(HERE, "raw"), exist_ok=True)
    json.dump(out, open(os.path.join(HERE, "raw", "raw-s2.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    # compact print
    for label, items in out.items():
        if isinstance(items, dict):
            continue
        print(f"\n== {label} ==")
        for r in items:
            print(f"  {r['year']} [{r['citations']}] {r.get('venue') or ''} | {r['title']} | {r.get('doi') or r.get('arxiv') or ''}")

if __name__ == "__main__":
    main()

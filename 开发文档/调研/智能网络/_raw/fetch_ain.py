# -*- coding: utf-8 -*-
"""AIN (AI for Networking, 子方向 IV) 检索器：arXiv + OpenAlex + Crossref。
用法: python fetch_ain.py [arxiv|openalex|crossref|all]
输出: _raw/raw-<source>.json 全量；stdout 打印紧凑清单。
"""
import sys, os, json, time, urllib.request, urllib.parse, xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
UA = "AIN-Research/1.0 (mailto:research@example.com)"

ARXIV_Q = [
    ("cls-traffic", 'ti:"traffic classification"'),
    ("cls-encrypted", 'ti:"encrypted traffic"'),
    ("pred-traffic", 'ti:"traffic prediction" AND cat:cs.NI'),
    ("anom-net", 'ti:"anomaly detection" AND cat:cs.NI'),
    ("ids", 'ti:"intrusion detection"'),
    ("cc-rl", 'ti:"congestion control" AND abs:"reinforcement learning"'),
    ("cc-learning", 'ti:"learning-based congestion control"'),
    ("llm-net", 'abs:"large language model" AND cat:cs.NI'),
    ("aiops", 'ti:"AIOps" OR ti:"root cause"'),
    ("te-rl", 'ti:"traffic engineering" AND abs:"reinforcement learning"'),
    ("routing-gnn", 'ti:"routing" AND abs:"graph neural network"'),
    ("ml-net-survey", 'ti:"machine learning for networking" OR ti:"deep learning for networking"'),
    ("digital-twin", 'ti:"digital twin" AND cat:cs.NI'),
    ("netagent", 'abs:"LLM agent" AND cat:cs.NI'),
]

OA_Q = [
    ("cls-encrypted", "encrypted traffic classification deep learning"),
    ("pred-traffic", "network traffic prediction deep learning"),
    ("ids", "network intrusion detection deep learning"),
    ("anom-net", "network anomaly detection deep learning"),
    ("cc-learning", "learning-based congestion control reinforcement learning"),
    ("llm-net", "large language model for networking"),
    ("aiops", "AIOps root cause analysis"),
    ("te-rl", "deep reinforcement learning traffic engineering routing"),
    ("gnn-net", "graph neural network networking survey"),
]

CR_Q = [
    ("cls-encrypted", "encrypted traffic classification deep learning"),
    ("pred-traffic", "network traffic prediction deep learning"),
    ("ids", "network intrusion detection deep learning survey"),
    ("cc-learning", "reinforcement learning congestion control"),
    ("llm-net", "large language model network management"),
    ("aiops", "AIOps intelligent network operations"),
    ("te-rl", "deep reinforcement learning traffic engineering"),
    ("gnn-net", "graph neural network for networking"),
]

def get(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()

def fetch_arxiv():
    out = {}
    for label, q in ARXIV_Q:
        url = ("http://export.arxiv.org/api/query?search_query=" + urllib.parse.quote(q)
               + "&start=0&max_results=25&sortBy=submittedDate&sortOrder=descending")
        try:
            xml = get(url).decode("utf-8", "replace")
            root = ET.fromstring(xml)
            ns = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
            items = []
            for e in root.findall("a:entry", ns):
                aid = e.find("a:id", ns).text.split("/abs/")[-1]
                pub = e.find("a:published", ns).text[:10]
                au = [a.find("a:name", ns).text for a in e.findall("a:author", ns)][:3]
                items.append({
                    "id": "arXiv:" + aid.split("v")[0],
                    "title": " ".join(e.find("a:title", ns).text.split()),
                    "year": pub,
                    "authors": au,
                    "url": "https://arxiv.org/abs/" + aid,
                    "pdf": "https://arxiv.org/pdf/" + aid,
                })
            out[label] = items
            print(f"[arXiv:{label}] {len(items)} hits ({q})")
        except Exception as ex:
            out[label] = {"error": str(ex)}
            print(f"[arXiv:{label}] ERROR {ex}")
        time.sleep(3)
    return out

def fetch_openalex():
    out = {}
    for label, q in OA_Q:
        url = ("https://api.openalex.org/works?search=" + urllib.parse.quote(q)
               + "&filter=from_publication_date:2024-01-01&sort=cited_by_count:desc&per_page=25&mailto=research@example.com")
        try:
            d = json.loads(get(url).decode("utf-8", "replace"))
            items = []
            for w in d.get("results", []):
                items.append({
                    "id": w.get("doi") or w.get("id"),
                    "title": w.get("title"),
                    "year": w.get("publication_year"),
                    "citations": w.get("cited_by_count"),
                    "venue": ((w.get("primary_location") or {}).get("source") or {}).get("display_name"),
                    "type": w.get("type"),
                    "url": w.get("doi") or w.get("id"),
                })
            out[label] = items
            print(f"[OpenAlex:{label}] {len(items)} hits ({q})")
        except Exception as ex:
            out[label] = {"error": str(ex)}
            print(f"[OpenAlex:{label}] ERROR {ex}")
        time.sleep(1)
    return out

def fetch_crossref():
    out = {}
    for label, q in CR_Q:
        url = ("https://api.crossref.org/works?query=" + urllib.parse.quote(q)
               + "&filter=from-pub-date:2024-01-01&sort=is-referenced-by-count&order=desc&rows=25"
               + "&mailto=research@example.com")
        try:
            d = json.loads(get(url).decode("utf-8", "replace"))
            items = []
            for w in d["message"]["items"]:
                items.append({
                    "id": w.get("DOI"),
                    "title": (w.get("title") or [None])[0],
                    "year": (w.get("issued", {}).get("date-parts") or [[None]])[0][0],
                    "citations": w.get("is-referenced-by-count"),
                    "venue": (w.get("container-title") or [None])[0],
                    "type": w.get("type"),
                    "url": "https://doi.org/" + w["DOI"] if w.get("DOI") else None,
                })
            out[label] = items
            print(f"[Crossref:{label}] {len(items)} hits ({q})")
        except Exception as ex:
            out[label] = {"error": str(ex)}
            print(f"[Crossref:{label}] ERROR {ex}")
        time.sleep(1)
    return out

def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    raw = os.path.join(HERE, "raw")
    os.makedirs(raw, exist_ok=True)
    if which in ("arxiv", "all"):
        d = fetch_arxiv(); json.dump(d, open(os.path.join(raw, "raw-arxiv.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if which in ("openalex", "all"):
        d = fetch_openalex(); json.dump(d, open(os.path.join(raw, "raw-openalex.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if which in ("crossref", "all"):
        d = fetch_crossref(); json.dump(d, open(os.path.join(raw, "raw-crossref.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

if __name__ == "__main__":
    main()

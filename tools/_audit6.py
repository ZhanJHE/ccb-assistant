import sys, json
sys.path.insert(0, "src"); sys.path.insert(0, "tests")
from pathlib import Path
from test_cli import _LibraryFixture
from ccb.core.model import ChannelRecord

fx = _LibraryFixture(); fx.setUp()
from ccb.library import Library as L
lib = L(fx.root)
ABST = ("We offload machine learning inference to programmable switches and SmartNICs; "
        "evaluation shows line-rate throughput but the switch has limited memory for KV caches.")
for i in range(2, 8):
    wid = lib.upsert_record(ChannelRecord(
        channel="manual", title=f"SmartNIC offload study {i}",
        authors=[f"Author {i}"], year=2022 + i % 3, venue="NSDI", doi=f"10.1000/net.{i}",
        abstract=ABST)).work_id
    lib.store_fulltext(wid, ABST + f" Study {i} reports caching results on the switch. ")
lib.close()

def run(argv):
    code, out, err = fx.run_cli(argv)
    keys, full = [], None
    if out.strip():
        try:
            d = json.loads(out)
            keys = sorted(d.keys()) if isinstance(d, dict) else ["<nd>"]
            full = d if isinstance(d, dict) else None
        except Exception: keys = ["<unparseable>"]
    return code, keys, full, err[:100]

c, k, d, e = run(["--offline", "topics", "survey", "smartnic offload", "--min-works", "1", "--min-fulltext", "0"])
sid = (d or {}).get("survey_id")
print("survey :", c, k, "| sid:", sid)
if sid:
    print("gaps   :", run(["--offline", "topics", "gaps", sid])[:2])
    c, k, d, e = run(["--offline", "topics", "candidates", sid])
    print("cands  :", c, k)
    rows = (d or {}).get("candidates") or []
    cid = (rows[0].get("candidate_id") or rows[0].get("id")) if rows else None
    print("cid:", cid, "| rows:", len(rows))
    if cid:
        c, k, d, e = run(["--offline", "topics", "draft", cid])
        print("draft  :", c, k)
        tid = (d or {}).get("topic_id")
        print("tid:", tid)
        if tid:
            print("rate   :", run(["--offline", "topics", "rate", tid])[:2])
            print("save   :", run(["--offline", "topics", "save", tid])[:2])
fx.tearDown()

import sys, json
sys.path.insert(0, "src"); sys.path.insert(0, "tests")
from pathlib import Path
from test_cli import _LibraryFixture
from ccb.core.model import ChannelRecord

fx = _LibraryFixture(); fx.setUp()
lib = L = None
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
    keys = []
    if out.strip():
        try:
            d = json.loads(out); keys = sorted(d.keys()) if isinstance(d, dict) else ["<nd>"]
        except Exception: keys = ["<unparseable>"]
    return code, keys, out[:250], err[:100]

print("merge :", run(["--offline", "merge", "doi:10.1000/cli.1", "doi:10.1000/net.2"]))
print("survey:", run(["--offline", "topics", "survey", "smartnic offload", "--min-works", "1", "--min-fulltext", "0"]))
c, k, o, e = run(["--offline", "topics", "survey", "smartnic offload", "--min-works", "1", "--min-fulltext", "0"])
sid = None
try: sid = json.loads(o).get("survey_id")
except Exception: pass
print("sid:", sid)
if sid:
    print("gaps  :", run(["--offline", "topics", "gaps", sid]))
    c, k, o, e = run(["--offline", "topics", "candidates", sid])
    print("cands :", c, k)
    cid = None
    try:
        rows = json.loads(o).get("candidates") or []
        if rows: cid = rows[0].get("candidate_id") or rows[0].get("id")
    except Exception: pass
    print("cid:", cid)
    if cid:
        print("draft :", run(["--offline", "topics", "draft", cid]))
        c, k, o, e = run(["--offline", "topics", "draft", cid])
        tid = None
        try: tid = json.loads(o).get("topic_id")
        except Exception: pass
        print("tid:", tid)
        if tid:
            print("rate  :", run(["--offline", "topics", "rate", tid]))
            print("save  :", run(["--offline", "topics", "save", tid]))
fx.tearDown()

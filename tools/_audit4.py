import sys, json
sys.path.insert(0, "src"); sys.path.insert(0, "tests")
from pathlib import Path
from test_cli import _LibraryFixture
from ccb.core.model import ChannelRecord

fx = _LibraryFixture(); fx.setUp()
lib = L = None
from ccb.library import Library as L
lib = L(fx.root)
for i in range(2, 8):
    lib.upsert_record(ChannelRecord(
        channel="manual",
        title=f"SmartNIC offload study {i}: in-network machine learning",
        authors=[f"Author {i}"], year=2022 + i % 3, venue="NSDI",
        doi=f"10.1000/net.{i}",
        abstract="We offload machine learning inference to programmable switches "
                 "and SmartNICs; evaluation shows line-rate throughput but limited "
                 "memory for KV caches on the switch.",
    ))
lib.close()

pdf = Path(fx.tmp / "tiny.pdf")
pdf.write_bytes(b"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj
4 0 obj<</Length 90>>stream
BT /F1 12 Tf 72 720 Td (Hello Planter in-network machine learning) Tj ET
endstream
endobj
5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj
trailer<</Root 1 0 R/Size 6>>
""")
def run(argv):
    code, out, err = fx.run_cli(argv)
    keys = []
    if out.strip():
        try:
            d = json.loads(out); keys = sorted(d.keys()) if isinstance(d, dict) else ["<nd>"]
        except Exception: keys = ["<unparseable>"]
    return code, keys, out[:200], err[:150]

print("add-file:", run(["--offline", "add-file", str(pdf), "--title", "Tiny Planter",
                        "--authors", "A", "--year", "2020", "--doi", "10.1000/tiny.1", "--extract"]))
print("open    :", run(["--offline", "open", "doi:10.1000/tiny.1", "--head", "200"]))
print("extract :", run(["--offline", "extract", "doi:10.1000/tiny.1"]))
print("merge   :", run(["--offline", "merge", "doi:10.1000/cli.1", "doi:10.1000/cli.2"]))
print("survey  :", run(["--offline", "topics", "survey", "smartnic offload", "--min-works", "1"]))
c, k, o, e = run(["--offline", "topics", "survey", "smartnic offload", "--min-works", "1"])
sid = None
try:
    sid = json.loads(o).get("survey_id")
except Exception: pass
if sid:
    print("gaps    :", run(["--offline", "topics", "gaps", sid]))
    c, k, o, e = run(["--offline", "topics", "candidates", sid])
    print("cands   :", c, k)
    try:
        rows = json.loads(o).get("candidates") or []
        if rows:
            cid = rows[0].get("candidate_id") or rows[0].get("id")
            print("draft   :", run(["--offline", "topics", "draft", cid]))
    except Exception as ex: print("chain:", ex)
fx.tearDown()

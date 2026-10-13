import sys, json, tempfile, shutil
sys.path.insert(0, "src"); sys.path.insert(0, "tests")
from pathlib import Path
from test_cli import _LibraryFixture
from ccb.cli._parser import build_parser

fx = _LibraryFixture(); fx.setUp()
wid = "doi:10.1000/cli.1"

# minimal 1-page PDF with a text layer (hand-crafted, engines are lenient)
pdf = b"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj
4 0 obj<</Length 90>>stream
BT /F1 12 Tf 72 720 Td (Hello Planter in-network machine learning) Tj ET
endstream
endobj
5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj
trailer<</Root 1 0 R/Size 6>>
"""
pdffile = fx.tmp / "tiny.pdf"
pdffile.write_bytes(pdf)

def run(argv):
    code, out, err = fx.run_cli(argv)
    keys = []
    if out.strip():
        try:
            d = json.loads(out)
            keys = sorted(d.keys()) if isinstance(d, dict) else ["<non-dict>"]
        except Exception:
            keys = ["<unparseable>"]
    return code, keys, out[:120]

print("get      :", run(["--offline", "get", wid]))
print("show     :", run(["--offline", "show", wid]))
print("cite     :", run(["--offline", "cite", wid]))
print("open     :", run(["--offline", "open", wid, "--head", "200"]))
print("index    :", run(["--offline", "index", "--ids", wid]))
print("add-file :", run(["--offline", "add-file", str(pdffile), "--title", "Tiny", "--authors", "A", "--year", "2020", "--doi", "10.1000/tiny.1", "--extract"]))
print("extract  :", run(["--offline", "extract", wid]))
print("find     :", run(["--offline", "find", "planter"]))
print("ask      :", run(["--offline", "ask", "planter"]))
print("get --with-pdf:", run(["--offline", "get", wid, "--with-pdf"]))

print("--- topics 链 ---")
c, k, o = run(["--offline", "topics", "survey", "networking", "--min-works", "1"])
print("survey   :", c, k)
sid = None
try:
    sid = json.loads(o).get("survey_id")
except Exception: pass
print("survey_id:", sid)
if sid:
    print("gaps     :", run(["--offline", "topics", "gaps", sid]))
    print("cands    :", run(["--offline", "topics", "candidates", sid]))
    c2, k2, o2 = run(["--offline", "topics", "candidates", sid])
    try:
        cands = json.loads(o2)
        rows = cands.get("candidates") or cands.get("rows") or []
        if rows:
            cid = rows[0].get("candidate_id") or rows[0].get("id")
            print("draft    :", run(["--offline", "topics", "draft", cid]))
    except Exception as e:
        print("chain stop:", e)
fx.tearDown()

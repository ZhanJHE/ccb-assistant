import sys, json, tempfile, shutil
sys.path.insert(0, "src"); sys.path.insert(0, "tests")
from pathlib import Path
from test_cli import _LibraryFixture
from ccb.core.model import ChannelRecord

fx = _LibraryFixture(); fx.setUp()
wid = "doi:10.1000/cli.1"

# seed fulltext so open succeeds
lib = Library = None
from ccb.library import Library as L
lib = L(fx.root)
w = lib.load(wid)
lib.store_fulltext(wid, "in-network machine learning planter offload text " * 40)
lib.close()

def run(argv):
    code, out, err = fx.run_cli(argv)
    keys = []
    if out.strip():
        try:
            d = json.loads(out)
            keys = sorted(d.keys()) if isinstance(d, dict) else ["<non-dict>"]
        except Exception:
            keys = ["<unparseable>"]
    return code, keys

print("open   :", run(["--offline", "open", wid, "--head", "200"]))
print("ask    :", run(["--offline", "ask", "planter offload"]))
print("check  :", run(["--offline", "check", "--all"]))

# merge: seed a second work with near-identical title? merge needs two ids: use the seeded one + create another
lib = L(fx.root)
lib.upsert_record(ChannelRecord(channel="manual", title="Second Work For Merge Testing",
                                authors=["B Two"], year=2021, doi="10.1000/cli.2"))
lib.close()
print("merge  :", run(["--offline", "merge", "--keep", wid, "--drop", "doi:10.1000/cli.2"]))

# install-skill in its own dir
d = Path(tempfile.mkdtemp(prefix="ccb-shape-"))
try:
    code, out, err = fx.run_cli(["--offline", "install-skill", "--library", str(fx.root)])
    # install-skill writes to CWD; chdir
    import os
    old = os.getcwd(); os.chdir(d)
    code, out, err = fx.run_cli(["install-skill"])
    os.chdir(old)
    keys = sorted(json.loads(out).keys()) if out.strip() else []
    print("install:", code, keys)
finally:
    shutil.rmtree(d, ignore_errors=True)
fx.tearDown()

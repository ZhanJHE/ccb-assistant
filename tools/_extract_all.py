import sys, subprocess, json
sys.path.insert(0, "src")
from ccb.library import Library
lib = Library("papers")
targets = []
for wid in lib.all_work_ids():
    w = lib.load(wid)
    if w is not None and w.has_pdf() and not w.has_fulltext():
        targets.append(wid)
lib.close()
print(f"to extract: {len(targets)}")
ok = fail = 0
for i, wid in enumerate(targets, 1):
    r = subprocess.run([sys.executable, "ccb.py", "get", wid, "--extract"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=300)
    if r.returncode in (0, 4):
        ok += 1
    else:
        fail += 1
        if fail <= 3:
            print(f"  FAIL {wid[:30]}: rc={r.returncode} {r.stderr.strip()[:80]}")
    if i % 20 == 0:
        print(f"  ... {i}/{len(targets)}")
print(f"extracted ok={ok} fail={fail}")

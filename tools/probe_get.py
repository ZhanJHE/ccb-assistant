"""Run the resolver's get() with full detail, to find where 404s originate.

Run: python tools/probe_get.py <identifier>
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from ccb.channels.registry import Registry  # noqa: E402
from ccb.library import Library  # noqa: E402
from ccb.resolver import Resolver  # noqa: E402


def main() -> int:
    ident = sys.argv[1] if len(sys.argv) > 1 else "arxiv:1706.03762"
    lib = Library(ROOT / ".ccb-probe")
    lib.init(force=True)
    reg = Registry(evidence=lib.evidence)
    res = Resolver(lib, reg)

    from ccb.ids import parse_identifier

    parsed = parse_identifier(ident)
    print(f"identifier : {ident!r}")
    print(f"parsed     : scheme={parsed.scheme!r} value={parsed.value!r}" if parsed else "parsed: None")
    print()
    print("lookup fan-out detail:")
    for chan in reg.usable("lookup"):
        ok = chan.supports_identifier(parsed.scheme if parsed else "")
        print(f"   {chan.name:14} supports={chan.supports!r:46} applicable={ok}")

    fan = res._fan_out_lookup(ident, channels="")
    print()
    print(f"lookup records : {len(fan['records'])}")
    for rec in fan["records"]:
        print(f"   {rec.channel:12} doi={rec.doi!r} arxiv={rec.arxiv_id!r} pdf={rec.pdf_url!r}")
    print(f"lookup errors  : {fan['errors']}")
    print(f"lookup warnings: {fan['warnings']}")

    out = res.get(ident, with_pdf=True)
    print()
    print(f"get source : {out.source}")
    print(f"get actions: {out.actions}")
    print(f"get errors : {out.errors}")
    print(f"get warns  : {out.warnings}")
    print(f"get msg    : {out.message}")
    if out.work:
        print(f"work_id    : {out.work.work_id}")
        print(f"ids        : {out.work.ids}")
        for m in out.work.manifestations:
            print(f"   manif {m.channel}: pdf_path={m.pdf_path!r} pdf_url={m.pdf_url!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

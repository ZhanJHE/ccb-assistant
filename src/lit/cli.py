"""The CLI — the only supported way to touch the library.

Design rules, all of them there because an agent is the primary caller:

* **JSON on stdout, always.** Prose goes to stderr. `--pretty` is for humans; the
  default is compact machine-readable output.
* **Exit codes are meaningful and few.** 0 success, 2 usage error, 3 not found,
  4 partial (some channels failed but the operation produced something), 5 hard
  failure. A caller can branch on them without parsing text.
* **Failures are never silent.** A gated, rate-limited or key-less channel appears in
  an `errors` map by name with a reason. "Nothing found" and "could not look" are
  different outcomes and are reported differently.
* **Idempotent.** Re-running any command converges; nothing depends on the caller
  having run a previous command.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Sequence

from . import __version__
from .channels import Registry
from .contract import contract, contract_text
from .extract import available_engines, extract_text
from .library import Library, default_library_root
from .resolver import Resolver
from .util import read_json, utc_now

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_NOT_FOUND = 3
EXIT_PARTIAL = 4
EXIT_FAILED = 5


class CommandError(Exception):
    """A failure with an exit code attached."""

    def __init__(self, message: str, code: int = EXIT_FAILED, **extra: Any):
        super().__init__(message)
        self.message = message
        self.code = code
        self.extra = extra


# --------------------------------------------------------------------------- #
# Context
# --------------------------------------------------------------------------- #


class Context:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        root = Path(args.library).expanduser() if args.library else default_library_root()
        self.library = Library(root)
        self.library.ensure()
        self.registry = Registry(
            evidence=self.library.evidence,
            verbose=bool(getattr(args, "verbose", False)),
            config_paths=_config_paths(self.library),
            enabled=_split(args.channel) if getattr(args, "channel", "") else None,
            disabled=_split(getattr(args, "disable_channel", "")),
        )
        self.resolver = Resolver(
            self.library,
            self.registry,
            offline=bool(getattr(args, "offline", False)),
            verbose=bool(getattr(args, "verbose", False)),
        )

    def emit(self, payload: dict[str, Any], code: int = EXIT_OK) -> int:
        if getattr(self.args, "pretty", False):
            sys.stdout.write(_render_pretty(payload) + "\n")
        else:
            sys.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        return code


def _config_paths(library: Library) -> list[Path]:
    paths: list[Path] = []
    env = os.environ.get("LIT_CHANNELS", "").strip()
    if env:
        paths.extend(Path(p) for p in env.split(os.pathsep) if p)
    paths.append(library.root / "channels.yaml")
    paths.append(Path.cwd() / "lit-channels.yaml")
    return paths


def _split(value: str) -> list[str]:
    return [v.strip() for v in (value or "").split(",") if v.strip()]


# --------------------------------------------------------------------------- #
# Handlers
# --------------------------------------------------------------------------- #


def cmd_channels(ctx: Context) -> int:
    args = ctx.args
    summary = ctx.registry.availability_summary()
    payload: dict[str, Any] = {
        "channels": ctx.registry.report(),
        "usable": summary["usable"],
        "unavailable": summary["unavailable"],
        "credentials_present": summary["credentials_present"],
        "note": (
            "Credential values are never read into output. 'unavailable' channels are "
            "skipped automatically; their reason tells you which environment variable "
            "would enable them."
        ),
    }
    if args.name:
        chan = ctx.registry.get(args.name)
        if chan is None:
            raise CommandError(
                f"unknown channel {args.name!r}", EXIT_NOT_FOUND,
                known=ctx.registry.names(),
            )
        payload = {"channel": chan.describe()}
    return ctx.emit(payload)


def cmd_contract(ctx: Context) -> int:
    if ctx.args.pretty:
        sys.stdout.write(contract_text() + "\n")
        return EXIT_OK
    return ctx.emit(contract())


def cmd_doctor(ctx: Context) -> int:
    report = ctx.library.self_check(repair=bool(ctx.args.repair))
    report["library_root"] = str(ctx.library.root)
    report["meta"] = ctx.library.meta()
    report["extractors"] = available_engines()
    summary = ctx.registry.availability_summary()
    report["channels_usable"] = summary["usable"]
    report["channels_unavailable"] = summary["unavailable"]
    code = EXIT_OK if not report.get("problems") else EXIT_PARTIAL
    return ctx.emit(report, code)


def cmd_repair(ctx: Context) -> int:
    report = ctx.library.repair()
    report["library_root"] = str(ctx.library.root)
    return ctx.emit(report, EXIT_OK if report.get("index_ok") else EXIT_FAILED)


def cmd_find(ctx: Context) -> int:
    args = ctx.args
    res = ctx.resolver.find(
        args.query,
        limit=args.limit,
        channels=args.source or "",
        year_from=args.year_from,
        year_to=args.year_to,
        local_first=not args.no_local,
        ingest=not args.no_ingest,
        min_local=args.min_local or 0,
    )
    payload = res.as_dict()
    if args.compact:
        payload["local_hits"] = [_compact(h) for h in payload["local_hits"]]
        payload["fetched"] = [_compact(h) for h in payload["fetched"]]
    # Exit-code semantics matter to a programmatic caller: producing results while some
    # channels failed is a *partial* success (4), not a failure (5). Only an empty
    # result set combined with errors is a genuine failure.
    produced = bool(res.local_hits or res.fetched)
    if not produced and res.errors:
        code = EXIT_FAILED
    elif res.errors and not res.local_answered:
        code = EXIT_PARTIAL
    else:
        code = EXIT_OK
    return ctx.emit(payload, code)


def cmd_get(ctx: Context) -> int:
    args = ctx.args
    res = ctx.resolver.get(
        args.identifier,
        with_pdf=args.with_pdf,
        refresh=args.refresh,
        channels=args.source or "",
        extract=bool(args.extract) or bool(args.with_pdf),
    )
    payload = res.as_dict(full=args.full)
    if not res.ok:
        return ctx.emit(payload, EXIT_NOT_FOUND)
    code = EXIT_PARTIAL if res.errors else EXIT_OK
    return ctx.emit(payload, code)


def cmd_ask(ctx: Context) -> int:
    """Retrieve passages that answer a question, with page-anchored citations."""
    args = ctx.args
    ids = _split(args.ids) if args.ids else None
    payload = ctx.resolver.ask(
        args.query,
        limit=args.limit,
        work_ids=ids,
        max_per_work=args.max_per_work,
    )
    if args.quotes_only:
        payload["hits"] = [
            {
                k: h[k]
                for k in ("work_id", "page", "start", "end", "score", "citation")
                if k in h
            }
            for h in payload["hits"]
        ]
    code = EXIT_OK if payload.get("grounded") else EXIT_NOT_FOUND
    return ctx.emit(payload, code)


def cmd_index(ctx: Context) -> int:
    """Build or refresh the passage index for stored full texts.

    `get --with-pdf` already indexes on extraction; this exists for a corpus that was
    populated before the index did, or after a full-text file was replaced.
    """
    from .passages import chunk_text

    args = ctx.args
    targets: list[str]
    if args.ids:
        targets = _split(args.ids)
    else:
        targets = [w.work_id for w in ctx.library.iter_works()]
    results: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for wid in targets:
        work = ctx.library.resolve(wid)
        if work is None:
            skipped.append({"work_id": wid, "reason": "not in the local library"})
            continue
        text = ctx.library.read_fulltext(work)
        if not text:
            skipped.append({"work_id": work.work_id, "reason": "no stored full text"})
            continue
        passages = chunk_text(text, work_id=work.work_id)
        rel, n = ctx.library.store_passages(work.work_id, passages)
        results.append(
            {
                "work_id": work.work_id,
                "passages": n,
                "pages": max((p.page for p in passages), default=0),
                "path": rel,
            }
        )
    payload: dict[str, Any] = {"indexed": results, "count": len(results)}
    if skipped:
        payload["skipped"] = skipped
    return ctx.emit(payload, EXIT_OK if results or not skipped else EXIT_NOT_FOUND)


def cmd_cite(ctx: Context) -> int:
    """Citation for one work, plus the provenance of the fields it used.

    The point of returning provenance alongside the citation is that a user can see
    *why* a field has the value it does — and notice when a field is missing because no
    source supplied it, rather than because the tool dropped it.
    """
    from .cite import to_bibtex, to_csl_json, to_ris

    args = ctx.args
    work = ctx.library.resolve(args.identifier)
    if work is None:
        raise CommandError(
            f"{args.identifier!r} not found in the local library "
            "(use `lit get` to acquire it first)",
            EXIT_NOT_FOUND,
        )
    fmt = (args.format or "bibtex").casefold()
    if fmt in ("bibtex", "bib"):
        rendered = to_bibtex(work, key_style=args.key_style)
    elif fmt == "ris":
        rendered = to_ris(work)
    elif fmt in ("csl", "csl-json", "json"):
        rendered = json.dumps(to_csl_json(work), ensure_ascii=False, indent=2)
    elif fmt in ("text", "plain"):
        from .cite import _plain

        rendered = _plain(work)
    else:
        raise CommandError(f"unsupported citation format {args.format!r}", EXIT_USAGE)
    missing = [
        f
        for f in ("title", "authors", "year", "venue", "doi")
        if not work.claims.get(f)
    ]
    return ctx.emit(
        {
            "work_id": work.work_id,
            "format": fmt,
            "citation": rendered,
            "provenance": {
                f: [c.src for c in work.claims.get(f, [])]
                for f in ("title", "authors", "year", "venue", "doi", "pages", "volume")
                if work.claims.get(f)
            },
            "unavailable_fields": missing,
            "note": (
                "Fields listed in unavailable_fields had no source, so they are omitted "
                "rather than guessed."
            ),
        }
    )


def cmd_open(ctx: Context) -> int:
    args = ctx.args
    work = ctx.library.resolve(args.identifier)
    if work is None:
        raise CommandError(
            f"{args.identifier!r} is not in the local library; run `lit get` first "
            "(or drop --offline)",
            EXIT_NOT_FOUND,
        )
    text = ctx.library.read_fulltext(work)
    if not text:
        # Deliberately does not silently go to the network: `open` means "read what is
        # local", and a caller wanting a download should say so.
        raise CommandError(
            f"no extracted full text stored for {work.work_id}; run "
            f"`lit get {args.identifier} --with-pdf`",
            EXIT_NOT_FOUND,
            work_id=work.work_id,
            has_pdf=work.has_pdf(),
        )
    total = len(text)
    if args.head:
        text = text[: args.head]
    payload = {
        "work_id": work.work_id,
        "title": work.title(),
        "chars": len(text),
        "total_chars": total,
        "text": text,
        "truncated": len(text) < total,
    }
    return ctx.emit(payload)


def cmd_show(ctx: Context) -> int:
    args = ctx.args
    work = ctx.library.resolve(args.identifier)
    if work is None:
        raise CommandError(f"{args.identifier!r} not found in the local library", EXIT_NOT_FOUND)
    if args.raw:
        return ctx.emit(work.as_dict())
    payload = work.summary()
    payload["manifestations_detail"] = [m.as_dict() for m in work.manifestations]
    payload["claim_conflicts"] = {
        f: {
            "display": (work.claims[f][0].val if work.claims.get(f) else None),
            "claims": [c.as_dict() for c in work.claims.get(f, [])],
        }
        for f in ("title", "year", "venue", "doi", "pages", "volume")
        if len(work.claims.get(f, [])) > 1
    }
    return ctx.emit(payload)


def cmd_search_local(ctx: Context) -> int:
    args = ctx.args
    hits = ctx.library.search(
        args.query,
        year_from=args.year_from,
        year_to=args.year_to,
        venue=args.venue or "",
        author=args.author or "",
        has_pdf=True if args.with_pdf else None,
        limit=args.limit,
    )
    return ctx.emit({"query": args.query, "hits": hits, "count": len(hits)})


def cmd_library(ctx: Context) -> int:
    args = ctx.args
    if args.action in ("stats", "report"):
        payload = ctx.library.stats()
        if args.action == "report":
            payload["pending_merges"] = ctx.library.unresolved_merges()
            payload["recent_events"] = ctx.library.ledger(limit=20)
        return ctx.emit(payload)
    if args.action == "list":
        rows = []
        for w in ctx.library.iter_works():
            rows.append(
                {
                    "work_id": w.work_id,
                    "title": w.title(),
                    "year": w.year(),
                    "venue": w.venue(),
                    "has_pdf": w.has_pdf(),
                    "updated_at": w.updated_at,
                }
            )
        rows.sort(key=lambda r: (r["year"] or 0, r["title"] or ""), reverse=True)
        if args.limit:
            rows = rows[: args.limit]
        return ctx.emit({"count": len(rows), "works": rows})
    if args.action == "merges":
        return ctx.emit({"pending": ctx.library.unresolved_merges()})
    raise CommandError(f"unknown library action {args.action!r}", EXIT_USAGE)


def cmd_check(ctx: Context) -> int:
    args = ctx.args
    ids = _split(args.ids) if args.ids else None
    if args.all:
        ids = None
    elif not ids:
        raise CommandError("specify work ids or --all", EXIT_USAGE)
    report = ctx.resolver.check(ids, limit=args.limit or 0)
    report["at"] = utc_now()
    code = EXIT_PARTIAL if report["unverifiable"] or report["errors"] else EXIT_OK
    return ctx.emit(report, code)


def cmd_check_files(ctx: Context) -> int:
    """Verify stored files: hash on disk must match the recorded hash."""
    from .util import sha256_bytes

    args = ctx.args
    report: dict[str, Any] = {"checked": 0, "ok": 0, "mismatch": [], "missing": [], "orphans": []}
    known: set[str] = set()
    for work in ctx.library.iter_works():
        for m in work.manifestations:
            if not m.pdf_path:
                continue
            report["checked"] += 1
            known.add(m.pdf_path.replace("/", os.sep))
            p = ctx.library.file_abs(m.pdf_path)
            if not p.exists():
                report["missing"].append({"work_id": work.work_id, "path": m.pdf_path})
                continue
            digest = sha256_bytes(p.read_bytes())
            if m.pdf_sha256 and digest != m.pdf_sha256:
                report["mismatch"].append(
                    {"work_id": work.work_id, "path": m.pdf_path,
                     "expected": m.pdf_sha256, "actual": digest}
                )
            else:
                report["ok"] += 1
    if ctx.library.files_dir.exists():
        for p in ctx.library.files_dir.glob("**/*"):
            if p.is_file():
                rel = str(p.relative_to(ctx.library.root)).replace("\\", "/")
                if rel not in known and rel.replace(os.sep, "/") not in known:
                    report["orphans"].append(rel)
    code = EXIT_PARTIAL if (report["mismatch"] or report["missing"]) else EXIT_OK
    return ctx.emit(report, code)


def cmd_export(ctx: Context) -> int:
    from .cite import export

    args = ctx.args
    if args.ids:
        works = []
        missing = []
        for wid in _split(args.ids):
            w = ctx.library.resolve(wid)
            if w is None:
                missing.append(wid)
            else:
                works.append(w)
        if missing and not works:
            raise CommandError(f"none of these are in the library: {missing}", EXIT_NOT_FOUND)
    else:
        works = list(ctx.library.iter_works())
        missing = []
    if args.query:
        needle = args.query.casefold()
        works = [w for w in works if needle in (w.title() + " " + w.abstract()).casefold()]
    text = export(works, fmt=args.format, key_style=args.key_style)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8", newline="\n")
        payload: dict[str, Any] = {
            "format": args.format, "entries": len(works), "path": str(Path(args.out).resolve())
        }
        if missing:
            payload["not_found"] = missing
        return ctx.emit(payload)
    # Stdout export is the raw citation text, not JSON: it is meant to be redirected.
    sys.stdout.write(text)
    return EXIT_OK


def cmd_add_file(ctx: Context) -> int:
    """Manually attach a PDF the user (or an agent) already has.

    This is the `manual` channel made concrete: local files enter the same library,
    with the same identity and provenance machinery, as anything fetched online.
    """
    args = ctx.args
    src = Path(args.file).expanduser()
    if not src.exists():
        raise CommandError(f"file not found: {src}", EXIT_NOT_FOUND)
    data = src.read_bytes()
    if not data.startswith(b"%PDF-") and not args.allow_non_pdf:
        raise CommandError(
            f"{src.name} does not look like a PDF (pass --allow-non-pdf to store anyway)",
            EXIT_USAGE,
        )
    title = args.title or src.stem
    from .model import ChannelRecord

    rec = ChannelRecord(
        channel="manual",
        title=title,
        authors=_split(args.authors) if args.authors else [],
        year=args.year,
        venue=args.venue or "",
        doi=args.doi or "",
        arxiv_id=args.arxiv or "",
        openreview_id=args.openreview or "",
        url=args.url or "",
        kind="record",
        extras={"local_file": str(src)},
    )
    upsert = ctx.library.upsert_record(rec)
    digest, rel, size = ctx.library.store_file(data, ext="pdf")
    ctx.library.attach_file(
        upsert.work_id,
        channel="manual",
        sha256=digest,
        rel_path=rel,
        size=size,
        external_id="",
    )
    ctx.library.log("manual_file_added", {"work_id": upsert.work_id, "file": str(src), "sha256": digest})
    payload = {
        "work_id": upsert.work_id,
        "action": upsert.action,
        "stored_path": rel,
        "sha256": digest,
        "bytes": size,
        "merge_candidates": upsert.merge_candidates,
    }
    if args.extract:
        work = ctx.library.load(upsert.work_id)
        if work is not None:
            payload["extraction"] = _extract_into(ctx.library, work.work_id)
    return ctx.emit(payload)


def cmd_extract(ctx: Context) -> int:
    args = ctx.args
    work = ctx.library.resolve(args.identifier)
    if work is None:
        raise CommandError(f"{args.identifier!r} not found in the local library", EXIT_NOT_FOUND)
    if not work.has_pdf():
        raise CommandError(
            f"{work.work_id} has no local PDF; run `lit get {args.identifier} --with-pdf`",
            EXIT_NOT_FOUND,
        )
    result = _extract_into(ctx.library, work.work_id, engine=args.engine or "")
    return ctx.emit({"work_id": work.work_id, **result})


def _extract_into(library: Library, work_id: str, *, engine: str = "") -> dict[str, Any]:
    """Extract, store text and rebuild the passage index — one implementation.

    This used to be duplicated here and in the resolver, and the two drifted: the CLI
    copy stored full text without building the passage index, so `lit extract` silently
    left `lit ask` searching stale passages. Delegating to the resolver keeps a single
    path, and the resolver applies the same invalidation rule as `get --with-pdf`.
    """
    from .channels import Registry
    from .resolver import Resolver

    resolver = Resolver(library, Registry(evidence=library.evidence), offline=True)
    if engine:
        # An explicit engine choice bypasses the per-page hybrid selection.
        return _extract_with_engine(library, work_id, engine=engine)
    return resolver._extract_text(library.load(work_id))  # type: ignore[arg-type]


def _extract_with_engine(library: Library, work_id: str, *, engine: str) -> dict[str, Any]:
    """Extract with one named engine, then store text and passages together."""
    from .passages import chunk_text
    from .util import sha256_text

    work = library.load(work_id)
    if work is None:
        return {"error": "work vanished"}
    best = work.best_pdf()
    if best is None or not best.pdf_path:
        return {"error": "no local PDF to extract"}
    ext = extract_text(library.file_abs(best.pdf_path), engine=engine, best_of=False)
    out = ext.as_dict()
    if ext.text:
        rel, chars = library.store_fulltext(work_id, ext.text)
        library.attach_fulltext(work_id, rel_path=rel, chars=chars, mid=best.mid)
        out["stored_path"] = rel
        out["chars"] = chars
        passages = chunk_text(ext.text, work_id=work_id)
        if passages:
            _, n = library.store_passages(
                work_id, passages, source_sha256=sha256_text(ext.text)
            )
            out["passages"] = n
            out["pages_indexed"] = max((p.page for p in passages), default=0)
    return out


def cmd_merge(ctx: Context) -> int:
    args = ctx.args
    result = ctx.library.merge(args.keep, args.drop, reason="cli")
    return ctx.emit(result)


def cmd_evidence(ctx: Context) -> int:
    args = ctx.args
    if args.id:
        text = ctx.library.evidence.render(args.id)
        return ctx.emit({"ev_id": args.id, "render": text})
    ids = ctx.library.evidence.ids()
    if args.limit:
        ids = ids[-args.limit:]
    return ctx.emit({"count": len(ids), "ids": ids})


def cmd_ledger(ctx: Context) -> int:
    args = ctx.args
    rows = ctx.library.ledger(limit=args.limit or 0, event=args.event or "")
    return ctx.emit({"count": len(rows), "events": rows})


def cmd_reindex(ctx: Context) -> int:
    return ctx.emit(ctx.library.reindex())


# --------------------------------------------------------------------------- #
# Parser
# --------------------------------------------------------------------------- #


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="lit",
        description=(
            "Aggregate every paper search/download channel behind one entry point, and "
            "keep a durable local library so nothing is fetched or parsed twice."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Run `lit contract` for the operating rules and the exact step order.\n"
            "Exit codes: 0 ok, 2 usage, 3 not found, 4 partial (some channels failed), "
            "5 failed."
        ),
    )
    p.add_argument("--version", action="version", version=f"lit {__version__}")
    p.add_argument("--library", help="library root (default: $LIT_HOME or ./.lit)")
    p.add_argument("--pretty", action="store_true", help="human-readable output instead of JSON")
    p.add_argument("--offline", action="store_true", help="never touch the network")
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--channel", help="comma-separated channel allow-list")
    p.add_argument("--disable-channel", help="comma-separated channels to disable")

    sub = p.add_subparsers(dest="command", required=True)

    sc = sub.add_parser("channels", help="list channels, availability and missing credentials")
    sc.add_argument("name", nargs="?", help="detail for one channel")
    sc.set_defaults(func=cmd_channels)

    sk = sub.add_parser("contract", help="the operating rules and canonical step order")
    sk.set_defaults(func=cmd_contract)

    sd = sub.add_parser("doctor", help="consistency report for the library")
    sd.add_argument("--repair", action="store_true", help="rebuild derived artefacts")
    sd.set_defaults(func=cmd_doctor)

    sr = sub.add_parser("repair", help="force a full rebuild of derived artefacts")
    sr.set_defaults(func=cmd_repair)

    sf = sub.add_parser("find", help="search: local library first, then channels")
    sf.add_argument("query")
    sf.add_argument("-n", "--limit", type=int, default=10)
    sf.add_argument("-s", "--source", help="channel selector: auto | all | a,b,c")
    sf.add_argument("--year-from", type=int, dest="year_from")
    sf.add_argument("--year-to", type=int, dest="year_to")
    sf.add_argument("--no-local", action="store_true", help="skip the local pass")
    sf.add_argument("--no-ingest", action="store_true", help="do not store channel results")
    sf.add_argument("--min-local", type=int, default=0,
                    help="only query channels when fewer than N local hits exist")
    sf.add_argument("--compact", action="store_true", help="trim records to key fields")
    sf.set_defaults(func=cmd_find)

    sg = sub.add_parser("get", help="acquire one paper: local first, then channels")
    sg.add_argument("identifier", help="DOI, arXiv id, OpenReview id, dblp key, PMID, URL, work_id")
    sg.add_argument("--with-pdf", action="store_true", dest="with_pdf")
    sg.add_argument("--extract", action="store_true", help="extract text after downloading")
    sg.add_argument("--refresh", action="store_true", help="re-query channels even if local")
    sg.add_argument("-s", "--source", help="channel selector")
    sg.add_argument("--full", action="store_true", help="include the full record, not a summary")
    sg.set_defaults(func=cmd_get)

    sa = sub.add_parser(
        "ask",
        help="retrieve passages that answer a question, with page-anchored citations",
    )
    sa.add_argument("query")
    sa.add_argument("-n", "--limit", type=int, default=5, help="passages to return")
    sa.add_argument("--ids", help="comma-separated work ids to search (default: whole library)")
    sa.add_argument("--max-per-work", type=int, default=2, dest="max_per_work",
                    help="diversity guard so one long paper cannot fill the results")
    sa.add_argument("--quotes-only", action="store_true", dest="quotes_only",
                    help="omit the passage text, keep the anchors and scores")
    sa.set_defaults(func=cmd_ask)

    si = sub.add_parser("index", help="build/refresh the passage index for stored full texts")
    si.add_argument("--ids", help="comma-separated work ids (default: whole library)")
    si.set_defaults(func=cmd_index)

    sc2 = sub.add_parser("cite", help="citation for one work, with field provenance")
    sc2.add_argument("identifier")
    sc2.add_argument("--format", default="bibtex",
                     choices=["bibtex", "ris", "csl", "json", "text"])
    sc2.add_argument("--key-style", default="authorYear", dest="key_style",
                     choices=["authorYear", "key", "hash"])
    sc2.set_defaults(func=cmd_cite)

    so = sub.add_parser("open", help="read local full text (never touches the network)")
    so.add_argument("identifier")
    so.add_argument("--head", type=int, default=0, help="only the first N characters")
    so.set_defaults(func=cmd_open)

    ss = sub.add_parser("show", help="show one stored record with its claim provenance")
    ss.add_argument("identifier")
    ss.add_argument("--raw", action="store_true", help="raw stored JSON")
    ss.set_defaults(func=cmd_show)

    sl = sub.add_parser("search-local", help="search only the local library")
    sl.add_argument("query", nargs="?", default="")
    sl.add_argument("-n", "--limit", type=int, default=25)
    sl.add_argument("--year-from", type=int, dest="year_from")
    sl.add_argument("--year-to", type=int, dest="year_to")
    sl.add_argument("--venue")
    sl.add_argument("--author")
    sl.add_argument("--with-pdf", action="store_true", dest="with_pdf")
    sl.set_defaults(func=cmd_search_local)

    slib = sub.add_parser("library", help="library-level views")
    slib.add_argument("action", choices=["stats", "report", "list", "merges"])
    slib.add_argument("-n", "--limit", type=int, default=0)
    slib.set_defaults(func=cmd_library)

    sck = sub.add_parser("check", help="re-verify stored records against the sources")
    sck.add_argument("ids", nargs="?", help="comma-separated work ids")
    sck.add_argument("--all", action="store_true")
    sck.add_argument("-n", "--limit", type=int, default=0)
    sck.set_defaults(func=cmd_check)

    scf = sub.add_parser("check-files", help="verify stored PDFs against recorded hashes")
    scf.set_defaults(func=cmd_check_files)

    se = sub.add_parser("export", help="export citations (bibtex/ris/csl/text)")
    se.add_argument("--format", default="bibtex")
    se.add_argument("--key-style", default="authorYear", dest="key_style",
                    choices=["authorYear", "key", "hash"])
    se.add_argument("--ids", help="comma-separated work ids (default: whole library)")
    se.add_argument("--query", help="substring filter over title/abstract")
    se.add_argument("-o", "--out", help="write to a file instead of stdout")
    se.set_defaults(func=cmd_export)

    saf = sub.add_parser("add-file", help="add a PDF you already have into the library")
    saf.add_argument("file")
    saf.add_argument("--title")
    saf.add_argument("--authors", help="semicolon-separated")
    saf.add_argument("--year", type=int)
    saf.add_argument("--venue")
    saf.add_argument("--doi")
    saf.add_argument("--arxiv")
    saf.add_argument("--openreview")
    saf.add_argument("--url")
    saf.add_argument("--extract", action="store_true")
    saf.add_argument("--allow-non-pdf", action="store_true", dest="allow_non_pdf")
    saf.set_defaults(func=cmd_add_file)

    sx = sub.add_parser("extract", help="extract text from a stored PDF")
    sx.add_argument("identifier")
    sx.add_argument("--engine", choices=["", "pdfplumber", "pypdf", "fitz"], default="")
    sx.set_defaults(func=cmd_extract)

    sm = sub.add_parser("merge", help="confirm a merge of two works")
    sm.add_argument("keep")
    sm.add_argument("drop")
    sm.set_defaults(func=cmd_merge)

    sev = sub.add_parser("evidence", help="inspect raw response snapshots")
    sev.add_argument("--id", help="render one snapshot")
    sev.add_argument("-n", "--limit", type=int, default=0)
    sev.set_defaults(func=cmd_evidence)

    sled = sub.add_parser("ledger", help="read the append-only audit trail")
    sled.add_argument("-n", "--limit", type=int, default=50)
    sled.add_argument("--event")
    sled.set_defaults(func=cmd_ledger)

    sri = sub.add_parser("reindex", help="rebuild the derived index (rarely needed)")
    sri.set_defaults(func=cmd_reindex)

    return p


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def _render_pretty(payload: dict[str, Any]) -> str:
    """Readable rendering for humans; never used by machine callers."""
    lines: list[str] = []
    for key in ("message", "note", "error"):
        if payload.get(key):
            lines.append(f"{key}: {payload[key]}")
    for chan, err in (payload.get("errors") or {}).items():
        lines.append(f"  ! {chan}: {err}")
    for warn in payload.get("warnings") or []:
        lines.append(f"  ~ {warn}")
    records = payload.get("local_hits") or payload.get("fetched") or payload.get("works")
    if records:
        lines.append("")
        for r in records:
            year = r.get("year") or "----"
            venue = r.get("venue") or ""
            flags = []
            if r.get("has_pdf"):
                flags.append("PDF")
            if r.get("has_fulltext"):
                flags.append("text")
            if r.get("local"):
                flags.append("local")
            flag_str = f" [{' '.join(flags)}]" if flags else ""
            lines.append(f"  {r.get('work_id', '?')}")
            lines.append(f"    {year}  {str(r.get('title', ''))[:110]}")
            if venue:
                lines.append(f"    {venue[:110]}")
            if flag_str:
                lines.append(f"    {flag_str.strip()}")
    if not lines:
        lines.append(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        ctx = Context(args)
    except Exception as exc:
        sys.stderr.write(json.dumps({"error": f"could not open the library: {exc}"}) + "\n")
        return EXIT_FAILED
    try:
        return args.func(ctx)
    except CommandError as exc:
        payload = {"error": exc.message, **exc.extra}
        if args.pretty:
            sys.stderr.write(f"error: {exc.message}\n")
        else:
            sys.stderr.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        return exc.code
    except BrokenPipeError:
        return EXIT_OK
    except KeyboardInterrupt:
        sys.stderr.write(json.dumps({"error": "interrupted"}) + "\n")
        return EXIT_FAILED
    except Exception as exc:
        payload = {"error": f"{type(exc).__name__}: {exc}"}
        if args.pretty:
            import traceback

            sys.stderr.write(traceback.format_exc())
        else:
            sys.stderr.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        return EXIT_FAILED


def _compact(record: dict[str, Any]) -> dict[str, Any]:
    keep = (
        "work_id", "title", "year", "venue", "doi", "arxiv_id", "openreview_id",
        "has_pdf", "has_fulltext", "local", "found_via", "authors",
    )
    out = {k: record[k] for k in keep if k in record}
    if isinstance(out.get("authors"), list) and len(out["authors"]) > 4:
        out["authors"] = out["authors"][:4] + ["et al."]
    return out


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

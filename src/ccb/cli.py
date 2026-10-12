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
from .contract import contract, contract_text
from .core.extract import available_engines, extract_text
from .core.paths import checkout_root
from .core.util import read_json, utc_now
from . import ops
from .library import Library, default_library_root
from .search import Registry, Resolver
from .topics import commands as topics_commands

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
            sys.stdout.write(
                _render_pretty(payload, _record_keys_for(self.args)) + "\n"
            )
        else:
            sys.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        return code


def _config_paths(library: Library) -> list[Path]:
    paths: list[Path] = []
    env = os.environ.get("CCB_CHANNELS", "").strip()
    if env:
        paths.extend(Path(p) for p in env.split(os.pathsep) if p)
    paths.append(library.root / "channels.yaml")
    # The checkout is a first-class location now that the library lives inside it:
    # a channel declaration committed next to the code travels with the clone. The
    # cwd entry stays for callers that carry a config with them.
    checkout = checkout_root()
    cwd = Path.cwd()
    if checkout is not None and checkout != cwd:
        paths.append(checkout / "ccb-channels.yaml")
    paths.append(cwd / "ccb-channels.yaml")
    return paths


def _split(value: str) -> list[str]:
    return [v.strip() for v in (value or "").split(",") if v.strip()]


def _not_found(ctx: Context, identifier: str) -> CommandError:
    """A not-found error that says what to do next.

    An empty library and a missing paper are different facts; a caller that cannot
    tell them apart retries the wrong thing. A fresh clone starts empty by design —
    the corpus is local data, never shipped in the repository — so the empty case is
    the *first* thing a new user hits, not an edge case.
    """
    if ctx.library.count() == 0:
        return CommandError(
            f"{identifier!r} is not in the library, and the library is empty. Acquire "
            f'something first: `ccb find "<topic>"` then `ccb get <id> --with-pdf`',
            EXIT_NOT_FOUND,
        )
    return CommandError(
        f"{identifier!r} not found in the local library; run `ccb find`/`ccb get` for it",
        EXIT_NOT_FOUND,
    )


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
        # What is missing, what it costs, and how to talk about it. A caller that only
        # hears "this channel is unavailable" cannot tell the user whether to go and find
        # a key or to carry on without one.
        "credentials_missing": summary["credentials_missing"],
        "credential_guidance": summary["credential_guidance"],
        "note": (
            "Credential values are never read into output. 'unavailable' channels are "
            "skipped automatically; their reason tells you which environment variable "
            "would enable them."
        ),
    }
    if summary.get("credentials_without_channel"):
        payload["credentials_without_channel"] = summary["credentials_without_channel"]
        payload["credentials_without_channel_note"] = summary[
            "credentials_without_channel_note"
        ]
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


def _legacy_libraries(library: Library) -> list[dict[str, Any]]:
    """Old ``.ccb`` libraries found next to the current root.

    The default moved from a hidden ``.ccb`` (resolved against the working directory)
    to a visible ``papers/`` (resolved against the checkout), so an existing corpus can
    be left behind by the change. It is *reported*, never moved: silently relocating
    someone's papers is worse than one extra line of output, and a wrong guess about
    which directory is authoritative corrupts a library rather than disappointing it.
    """
    found: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for base in (library.root.parent, Path.cwd(), checkout_root()):
        if base is None:
            continue
        legacy = base / ".ccb"
        try:
            key = legacy.resolve()
        except OSError:  # pragma: no cover - unreadable path
            continue
        if key in seen or not (legacy / "library.json").is_file():
            continue
        seen.add(key)
        works_dir = legacy / "works"
        count = sum(1 for _ in works_dir.rglob("*.json")) if works_dir.is_dir() else 0
        found.append(
            {
                "path": str(legacy),
                "works": count,
                "note": "an older library; it is untouched and not read from",
                "hint": f'set CCB_HOME="{legacy}" (or pass --library) to keep using it',
            }
        )
    return found


def cmd_doctor(ctx: Context) -> int:
    report = ctx.library.self_check(repair=bool(ctx.args.repair))
    report["library_root"] = str(ctx.library.root)
    report["meta"] = ctx.library.meta()
    report["extractors"] = available_engines()
    summary = ctx.registry.availability_summary()
    report["channels_usable"] = summary["usable"]
    report["channels_unavailable"] = summary["unavailable"]
    legacy = _legacy_libraries(ctx.library)
    if legacy:
        report["legacy_libraries"] = legacy
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
    # `grounded: false` means the corpus does not cover the question — that is a
    # *successful* retrieval reporting a gap, not a failed command. It used to return
    # EXIT_NOT_FOUND (3), the same code as "this identifier is not in the library",
    # which conflated two facts the `never-answer-from-memory` invariant requires the
    # caller to tell apart. The payload carries `outcome` for that branch instead.
    return ctx.emit(payload, EXIT_OK)


def cmd_index(ctx: Context) -> int:
    """Build or refresh the passage index for stored full texts.

    `get --with-pdf` already indexes on extraction; this exists for a corpus that was
    populated before the index did, or after a full-text file was replaced.
    """
    from .library.passages import chunk_text

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
    from .library.cite import to_bibtex, to_csl_json, to_ris

    args = ctx.args
    work = ctx.library.resolve(args.identifier)
    if work is None:
        raise _not_found(ctx, args.identifier)
    fmt = (args.format or "bibtex").casefold()
    if fmt in ("bibtex", "bib"):
        rendered = to_bibtex(work, key_style=args.key_style)
    elif fmt == "ris":
        rendered = to_ris(work)
    elif fmt in ("csl", "csl-json", "json"):
        rendered = json.dumps(to_csl_json(work), ensure_ascii=False, indent=2)
    elif fmt in ("text", "plain"):
        from .library.cite import _plain

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
            f"{args.identifier!r} is not in the local library; run `ccb get` first "
            "(or drop --offline)",
            EXIT_NOT_FOUND,
        )
    text = ctx.library.read_fulltext(work)
    if not text:
        # Deliberately does not silently go to the network: `open` means "read what is
        # local", and a caller wanting a download should say so.
        raise CommandError(
            f"no extracted full text stored for {work.work_id}; run "
            f"`ccb get {args.identifier} --with-pdf`",
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
        raise _not_found(ctx, args.identifier)
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
    from .core.util import sha256_bytes

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
    from .library.cite import export

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
    # Stdout is JSON like every other command. `--raw` is the explicit opt-in for the
    # redirectable form (`ccb export --raw > refs.bib`), because the previous behaviour —
    # raw text by default — broke the one contract every caller relies on, and on an
    # empty library it printed nothing at all while still exiting 0.
    if args.raw:
        sys.stdout.write(text)
        return EXIT_OK
    payload = {"format": args.format, "entries": len(works), "text": text}
    if missing:
        payload["not_found"] = missing
    return ctx.emit(payload)


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
    from .core.model import ChannelRecord

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
        raise _not_found(ctx, args.identifier)
    if not work.has_pdf():
        raise CommandError(
            f"{work.work_id} has no local PDF; run `ccb get {args.identifier} --with-pdf`",
            EXIT_NOT_FOUND,
        )
    # `has_pdf` reads the *record*, not the disk. A PDF that was deleted by hand — or
    # a `files/` directory that never came along — would otherwise reach the extractor
    # as a missing path and surface as an engine traceback instead of an instruction.
    best = work.best_pdf()
    if best is not None and best.pdf_path and not ctx.library.file_abs(best.pdf_path).exists():
        raise CommandError(
            f"{work.work_id} records a PDF at {best.pdf_path}, but the file is not "
            f"there; run `ccb get {args.identifier} --with-pdf` to fetch it again",
            EXIT_NOT_FOUND,
        )
    result = _extract_into(ctx.library, work.work_id, engine=args.engine or "")
    return ctx.emit({"work_id": work.work_id, **result})


def _extract_into(library: Library, work_id: str, *, engine: str = "") -> dict[str, Any]:
    """Extract, store text and rebuild the passage index — one implementation.

    This used to be duplicated here and in the resolver, and the two drifted: the CLI
    copy stored full text without building the passage index, so `ccb extract` silently
    left `ccb ask` searching stale passages. Delegating to the resolver keeps a single
    path, and the resolver applies the same invalidation rule as `get --with-pdf`.
    """
    from .search import Registry
    from .search import Resolver

    resolver = Resolver(library, Registry(evidence=library.evidence), offline=True)
    if engine:
        # An explicit engine choice bypasses the per-page hybrid selection.
        return _extract_with_engine(library, work_id, engine=engine)
    return resolver._extract_text(library.load(work_id))  # type: ignore[arg-type]


def _extract_with_engine(library: Library, work_id: str, *, engine: str) -> dict[str, Any]:
    """Extract with one named engine, then store text and passages together."""
    from .library.passages import chunk_text
    from .core.util import sha256_text

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
    try:
        result = ctx.library.merge(args.keep, args.drop, reason="cli")
    except KeyError as exc:
        # `Library.merge` guards its own contract with KeyError, which is right for a
        # programmer calling the API. From the CLI the same condition is a typo, and it
        # used to surface as an unhandled exception: exit 5 plus a traceback instead of
        # "these ids are not in the library".
        detail = exc.args[0] if exc.args else str(exc)
        raise CommandError(str(detail), EXIT_NOT_FOUND) from exc
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


def cmd_topics(ctx: Context) -> int:
    """Mine the corpus for one research topic worth doing.

    Exit codes carry the distinction an agent needs to branch on: 4 when the survey
    ran but the corpus is too thin to mine, 3 when there is nothing to return, 0
    otherwise. A thin corpus is a real answer, not a failure.
    """
    args = ctx.args
    action = str(getattr(args, "topics_action", ""))
    payload = topics_commands.run(action, ctx.library, ctx.resolver, args)
    error = payload.get("error")
    if error:
        code = (
            EXIT_NOT_FOUND
            if error in ("unknown_survey", "unknown_topic", "unknown_candidate")
            else EXIT_FAILED
        )
        return ctx.emit(payload, code)
    if action == "survey" and not payload.get("sufficient", True):
        return ctx.emit(payload, EXIT_PARTIAL)
    if action == "gaps" and not payload.get("usable", True):
        return ctx.emit(payload, EXIT_NOT_FOUND)
    if action == "candidates" and not payload.get("candidates"):
        return ctx.emit(payload, EXIT_NOT_FOUND)
    return ctx.emit(payload)


# --------------------------------------------------------------------------- #
# Operations -> argparse
# --------------------------------------------------------------------------- #


def _add_params(sp: argparse.ArgumentParser, op: ops.Operation) -> None:
    """Declare one operation's parameters on its subparser.

    Derived from the same declarations the MCP schema and the contract use, so a new
    parameter cannot exist on one face and be missing on another. ``mcp_only`` params are
    skipped: the CLI reaches those through a global flag instead.
    """
    for param in op.params:
        if param.mcp_only:
            continue
        kwargs: dict[str, Any] = {}
        if param.help:
            kwargs["help"] = param.help
        if param.choices:
            kwargs["choices"] = list(param.choices)
        if param.kind == "flag":
            sp.add_argument(*param.cli.split("|"), action="store_true",
                            dest=param.argparse_dest, default=param.default, **kwargs)
        elif param.cli:
            sp.add_argument(*param.cli.split("|"), dest=param.argparse_dest,
                            type=int if param.kind == "int" else str,
                            default=param.default, **kwargs)
        elif param.required:
            sp.add_argument(param.name, **kwargs)
        else:
            sp.add_argument(param.name, nargs="?", default=param.default, **kwargs)


def _add_operations(sub: Any, common: argparse.ArgumentParser) -> None:
    """Build every subparser from ``ccb.ops``.

    Grouped operations (``library``, ``topics``) get a parent subcommand whose nested
    subparsers carry the actions, and each parent declares the ``dest`` its handler
    already reads, so ``args.action`` and ``args.topics_action`` keep working.
    """
    handlers = {name: obj for name, obj in globals().items() if name.startswith("cmd_")}
    nesting: dict[str, Any] = {}
    for op in ops.OPERATIONS:
        if op.group:
            target = nesting.get(op.group)
            if target is None:
                info = ops.GROUP_INFO[op.group]
                parent = sub.add_parser(op.group, parents=[common], help=info["help"],
                                        description=info.get("description"))
                target = parent.add_subparsers(dest=info["dest"], required=True)
                nesting[op.group] = target
        else:
            target = sub
        sp = target.add_parser(op.name, parents=[common], help=op.summary)
        _add_params(sp, op)
        sp.set_defaults(func=handlers[op.handler])



def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ccb",
        description=(
            "Aggregate every paper search/download channel behind one entry point, and "
            "keep a durable local library so nothing is fetched or parsed twice."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Run `ccb contract` for the operating rules and the exact step order.\n"
            "Exit codes: 0 ok, 2 usage, 3 not found, 4 partial (some channels failed), "
            "5 failed."
        ),
    )
    p.add_argument("--version", action="version", version=f"ccb {__version__}")
    p.add_argument("--library", help="library root (default: $CCB_HOME, else <checkout>/papers)")
    p.add_argument("--pretty", action="store_true", help="human-readable output instead of JSON")
    p.add_argument("--offline", action="store_true", help="never touch the network")
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--channel", help="comma-separated channel allow-list")
    p.add_argument("--disable-channel", help="comma-separated channels to disable")

    # The same global flags are attached to every subparser so they may appear *after*
    # the subcommand as well. argparse only accepts them before it, which trips everyone
    # who appends `--pretty` to the command they just typed — including the probe script
    # written for this repository. Each copy defaults to SUPPRESS so an absent occurrence
    # leaves the value parsed at the top level untouched.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--library", default=argparse.SUPPRESS,
                        help="library root (default: $CCB_HOME, else <checkout>/papers)")
    common.add_argument("--pretty", action="store_true", default=argparse.SUPPRESS,
                        help="human-readable output instead of JSON")
    common.add_argument("--offline", action="store_true", default=argparse.SUPPRESS,
                        help="never touch the network")
    common.add_argument("--verbose", action="store_true", default=argparse.SUPPRESS)
    common.add_argument("--channel", default=argparse.SUPPRESS,
                        help="comma-separated channel allow-list")
    common.add_argument("--disable-channel", default=argparse.SUPPRESS,
                        help="comma-separated channels to disable")

    sub = p.add_subparsers(dest="command", required=True)
    _add_operations(sub, common)

    return p


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def _record_keys_for(args: argparse.Namespace) -> tuple[str, ...]:
    """Which payload keys hold record lists, for the operation that just ran.

    Declared by the operation in ``ccb.ops``, never inferred from the payload: `works`
    is a count in ``library stats`` and a list in ``library list``, and the renderer used
    to guess between them and crash.
    """
    command = getattr(args, "command", "") or ""
    action = getattr(args, "action", "") or getattr(args, "topics_action", "") or ""
    op = ops.BY_PATH.get(f"{command} {action}" if action else command)
    return op.records_key if op else ()


def _render_pretty(payload: dict[str, Any], record_keys: tuple[str, ...] = ()) -> str:
    """Readable rendering for humans; never used by machine callers.

    Which payload keys hold record lists is *declared by the command that produced the
    payload*, not inferred here. The previous version guessed with
    ``local_hits or fetched or works`` and crashed on ``library stats``, where ``works``
    is a count — the same key means different things in different commands, so a renderer
    that sniffs shapes will eventually meet a payload that breaks it. The type is still
    checked before iterating, because a declared key can legitimately hold a scalar.
    """
    lines: list[str] = []
    for key in ("message", "note", "error"):
        if payload.get(key):
            lines.append(f"{key}: {payload[key]}")
    for chan, err in (payload.get("errors") or {}).items():
        lines.append(f"  ! {chan}: {err}")
    for warn in payload.get("warnings") or []:
        lines.append(f"  ~ {warn}")
    for key in record_keys:
        rows = payload.get(key)
        if not isinstance(rows, list) or not rows:
            continue
        lines.append("")
        if len(record_keys) > 1:
            lines.append(f"  {key}:")
        for r in rows:
            if not isinstance(r, dict):
                lines.append(f"  {r}")
                continue
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

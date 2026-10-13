"""Bridge to a locally installed multi-source CLI (the 21-source `paper-search`).

Why a bridge instead of an HTTP channel: that tool already covers 21 sources —
including ones that are awkward to talk to directly (BASE, CiteSeerX, OpenAIRE,
SSRN, HAL, IACR, Zenodo) — so re-implementing them would be duplicated effort and
strictly worse. Shelling out keeps it an *option*: if the executable is missing, the
channel reports itself unavailable and every other channel keeps working.

Runtime realities this handles, all observed on this machine:

* the tool must be invoked through its ``.cmd`` wrapper (or with ``PYTHONUTF8=1``)
  because the Windows console code page is GBK and PDF text extraction aborts with
  ``'gbk' codec can't encode character`` on any paper containing accents or maths;
* its diagnostics ("No CORE API key provided") are written to **stderr while the
  command still succeeds**, so the exit code alone is not the verdict;
* its JSON envelope is ``{papers, source_results, errors, total}`` and the ``errors``
  map explains a thin result set — worth surfacing rather than swallowing.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # annotation only; the parser imports the model where it runs
    from ...core.model import ChannelRecord

from .base import (
    CAP_LOOKUP,
    CAP_PDF,
    CAP_SEARCH,
    Channel,
    ChannelResult,
    ChannelSpec,
)

DEFAULT_CANDIDATES = (
    "paper-search",
    "paper-search-cli",
)


class PaperSearchChannel(Channel):
    # The CLI's only lookup path is a targeted search: fine for identifiers, not
    # for a bare title.
    supports = ("doi", "arxiv", "pmid", "openreview", "dblp", "acl", "pmlr", "url")

    spec = ChannelSpec(
        name="paper_search",
        kind="cli",
        title="Local paper-search CLI (21 sources)",
        caps=(CAP_SEARCH, CAP_LOOKUP, CAP_PDF),
        auth="env:PAPER_SEARCH_CORE_API_KEY?",
        license="MIT (the tool itself); per-source data licences apply",
        rate_rps=0.5,
        notes=(
            "Bridges an already-installed multi-source CLI. Adds coverage for sources "
            "this project talks to directly (arXiv, Crossref, OpenAlex, dblp, "
            "Europe PMC) plus BASE, CiteSeerX, OpenAIRE, SSRN, HAL, IACR and Zenodo. "
            "Optional keys (CORE_API_KEY, DOAJ_API_KEY, UNPAYWALL_EMAIL) only raise "
            "rate limits. No paywall circumvention is used."
        ),
        config={"candidates": list(DEFAULT_CANDIDATES)},
    )

    # ------------------------------------------------------------------ #

    def _executable(self) -> str:
        override = os.environ.get("CCB_PAPER_SEARCH", "").strip()
        if override and os.path.exists(override):
            return override
        from .generic import _resolve_command

        for cand in self.spec.config.get("candidates", DEFAULT_CANDIDATES):
            # Prefer the .cmd wrapper on Windows: it sets UTF-8 I/O before exec'ing.
            for name in (cand + ".cmd", cand) if os.name == "nt" else (cand,):
                found = _resolve_command(name)
                if found:
                    return found
        return ""

    def available(self) -> tuple[bool, str]:
        usable, reason = super().available()
        if not usable:
            return usable, reason
        if not self._executable():
            return False, (
                "local paper-search CLI not found (install it, or set "
                "CCB_PAPER_SEARCH to its path)"
            )
        return True, ""

    # ------------------------------------------------------------------ #

    def _run(self, args: list[str]) -> tuple[Any | None, ChannelResult]:
        import json
        import subprocess

        exe = self._executable()
        res = ChannelResult(self.name, queries=[{"command": [exe] + args}])
        if not exe:
            res.error = "paper-search CLI not found"
            return None, res
        env = dict(os.environ)
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        try:
            proc = subprocess.run(
                [exe] + args,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=240,
                env=env,
                shell=exe.casefold().endswith((".cmd", ".bat")),
            )
        except subprocess.TimeoutExpired:
            res.error = "paper-search timed out after 240s"
            self.snapshot(command=[exe] + args, error=res.error, notes="paper_search timeout")
            return None, res
        except OSError as exc:
            res.error = f"could not run paper-search: {exc}"
            return None, res
        res.ev_id = self.snapshot(
            command=[exe] + args,
            body=proc.stdout or "",
            status=proc.returncode,
            error="" if proc.returncode == 0 else (proc.stderr or "")[:400],
            notes="paper_search",
        )
        # Informational diagnostics on stderr are normal even on success; keep them
        # as warnings so a caller can see that, say, Unpaywall was skipped.
        for line in (proc.stderr or "").splitlines():
            line = line.strip()
            if line and not line.startswith("{"):
                res.warnings.append(line[:200])
        if not (proc.stdout or "").strip():
            res.error = (
                (proc.stderr or "").strip()[:400] or f"no output (exit {proc.returncode})"
            )
            return None, res
        try:
            return json.loads(proc.stdout), res
        except json.JSONDecodeError as exc:
            res.error = f"paper-search did not emit JSON: {exc}"
            return None, res

    # ------------------------------------------------------------------ #

    def search(
        self,
        query: str,
        *,
        limit: int = 10,
        year_from: int | None = None,
        year_to: int | None = None,
        sources: str = "",
        **kw: Any,
    ) -> ChannelResult:
        args = ["search", query, "-n", str(max(1, limit))]
        if sources:
            args += ["-s", sources]
        if year_from or year_to:
            args += ["-y", f"{year_from or ''}-{year_to or ''}"]
        data, res = self._run(args)
        if data is None:
            return res
        self._extract(data, res, limit=limit)
        return res

    def lookup(self, identifier: str, *, source: str = "", **kw: Any) -> ChannelResult:
        """Resolve via a targeted search; the CLI has no identifier-lookup subcommand.

        Deliberately narrow: a title is not a safe lookup key, so only identifier
        shapes are accepted, and the caller is told to use the native channel for the
        corresponding source when precision matters.
        """
        from ...core.ids import parse_identifier

        parsed = parse_identifier(identifier)
        if parsed is None:
            return ChannelResult(self.name, error=f"unrecognized identifier: {identifier!r}")
        if parsed.scheme in ("title", "url"):
            return ChannelResult(
                self.name,
                error=(
                    f"paper_search cannot look up a {parsed.scheme}; use the native "
                    "channel for that identifier (e.g. crossref for a DOI, arxiv for "
                    "an arXiv id)"
                ),
            )
        # Constrain the fan-out. The CLI defaults to all 21 sources, which for a single
        # known identifier means 21 HTTP calls, several 429s and a long wait (measured
        # at tens of seconds, with SSRN, CiteSeerX, dblp and Semantic Scholar all
        # failing). An identifier lookup only needs the source that owns it.
        if not source:
            source = {
                "arxiv": "arxiv",
                "pmid": "pubmed",
                "openreview": "openreview",
                "acl": "semantic",
                "pmlr": "semantic",
                "openalex": "openalex",
            }.get(parsed.scheme, "")
        args = ["search", parsed.value, "-n", "5"]
        if source:
            args += ["-s", source]
        data, res = self._run(args)
        if data is None:
            return res
        self._extract(data, res, limit=5)
        return res

    def _extract(self, data: Any, res: ChannelResult, *, limit: int) -> None:
        papers = data.get("papers") if isinstance(data, dict) else None
        if not isinstance(papers, list):
            # A bare list is also accepted, for forward compatibility.
            papers = data if isinstance(data, list) else None
        if papers is None:
            res.error = "paper-search output had no 'papers' list"
            return
        if isinstance(data, dict):
            total = data.get("total")
            if isinstance(total, int):
                res.total_available = total
            errors = data.get("errors")
            if isinstance(errors, dict):
                for src, msg in errors.items():
                    if msg:
                        res.warnings.append(f"{src}: {str(msg)[:160]}")
            if not papers and data.get("errors"):
                res.warnings.append(
                    "every source reported an error; see per-source warnings above"
                )
        for item in papers[:limit]:
            if not isinstance(item, dict):
                continue
            rec = self._parse_paper(item, res.ev_id)
            if rec is not None:
                res.records.append(rec)

    def _parse_paper(self, item: dict[str, Any], ev_id: str) -> "ChannelRecord | None":
        from ...core.model import ChannelRecord
        from ...core.util import strip_latex

        title = strip_latex(str(item.get("title") or "")).strip()
        if not title:
            return None
        authors = item.get("authors")
        if isinstance(authors, str):
            authors = [a.strip() for a in authors.split(";") if a.strip()]
        elif isinstance(authors, list):
            authors = [str(a).strip() for a in authors if a]
        else:
            authors = []
        year = None
        for key in ("published_date", "published", "year"):
            raw = item.get(key)
            if raw:
                import re

                m = re.search(r"(19|20)\d{2}", str(raw))
                if m:
                    year = int(m.group(0))
                    break
        categories = item.get("categories")
        if isinstance(categories, list):
            categories = ", ".join(str(c) for c in categories[:3])
        native = str(item.get("paper_id") or "")
        src = str(item.get("source") or "")
        return ChannelRecord(
            channel=self.name,
            title=title,
            authors=authors,
            year=year,
            venue=str(item.get("venue") or categories or ""),
            abstract=strip_latex(str(item.get("abstract") or "")).strip(),
            doi=str(item.get("doi") or ""),
            arxiv_id=native if src == "arxiv" else "",
            pmid=native if src in ("pubmed", "pmc") else "",
            url=str(item.get("url") or ""),
            pdf_url=str(item.get("pdf_url") or ""),
            kind="record",
            ev=ev_id,
            extras={
                "channel_source": src,
                "native_id": native,
                "citations": item.get("citations"),
            },
        )

    def download_pdf(self, rec: ChannelRecord, **kw: Any) -> tuple[bytes, str, str]:
        """Download through the CLI into a temp dir, then hand back the bytes."""
        import tempfile

        native = rec.extras.get("native_id")
        src = rec.extras.get("channel_source")
        if not native or not src:
            return super().download_pdf(rec, **kw)
        with tempfile.TemporaryDirectory(prefix="ccb-ps-") as tmp:
            data, res = self._run(["download", str(src), str(native), "-o", tmp])
            if data is None:
                return b"", "", res.error
            path = ""
            if isinstance(data, dict):
                path = str(data.get("path") or "")
            if not path or not os.path.exists(path):
                return b"", "", "paper-search did not report a readable downloaded file"
            try:
                with open(path, "rb") as fh:
                    return fh.read(), path, ""
            except OSError as exc:
                return b"", path, f"could not read downloaded file: {exc}"

"""Declarative channels — add a source without writing Python.

The registry reads ``channels.yaml`` and can instantiate three kinds of channel:

* ``kind: http`` — a request template plus dot-path field mappings. Enough for the
  majority of scholarly APIs (Europe PMC, Semantic Scholar, Unpaywall, DBLP mirrors,
  institutional repositories).
* ``kind: cli`` — bridge an already-installed command-line tool (this is how the
  local 21-source ``paper-search`` is wired in without depending on MCP).
* ``kind: mcp`` — call a Model Context Protocol server over stdio.

Everything here is deliberately *declarative and forgiving*: an unknown or missing
field yields an empty value rather than an exception, because a partially-mapped
external source is still useful and a crashing one is not.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from typing import Any

from ...core.model import ChannelRecord
from .base import (
    Channel,
    ChannelResult,
    ChannelSpec,
)


def _dig(data: Any, path: str, default: Any = None) -> Any:
    """Resolve a dot path against nested dicts/lists.

    Supports ``a.b.0.c``, ``a.*.c`` (first value found across a list) and a leading
    ``@`` meaning "search recursively for the first matching key", which covers APIs
    whose envelope depth varies between responses.
    """
    if not path:
        return default
    if path.startswith("@"):
        return _find_key(data, path[1:], default)
    cur = data
    for part in path.split("."):
        if cur is None:
            return default
        if part == "*":
            if isinstance(cur, list):
                cur = cur[0] if cur else None
                continue
            return default
        if isinstance(cur, list):
            try:
                cur = cur[int(part)]
                continue
            except (ValueError, IndexError):
                return default
        if isinstance(cur, dict):
            if part not in cur:
                return default
            cur = cur[part]
            continue
        return default
    return cur if cur is not None else default


def _find_key(data: Any, key: str, default: Any = None) -> Any:
    if isinstance(data, dict):
        if key in data:
            return data[key]
        for v in data.values():
            found = _find_key(v, key, default)
            if found is not default:
                return found
    elif isinstance(data, list):
        for item in data:
            found = _find_key(item, key, default)
            if found is not default:
                return found
    return default


def _as_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(str(value)[:4])
    except (TypeError, ValueError):
        return None


def _as_list(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [str(v) for v in value if v not in (None, "")]
    return [str(value)]


class _DeclaredChannel(Channel):
    """Shared plumbing for config-declared channels."""

    def __init__(self, name: str, spec: dict[str, Any], **kw: Any):
        self.name_ = name
        self.decl = spec
        auth = spec.get("auth", "none")
        caps = tuple(spec.get("caps") or ())
        self.spec = ChannelSpec(
            name=name,
            kind=str(spec.get("kind", "http")),
            title=str(spec.get("title", name)),
            caps=caps,
            auth=str(auth),
            license=str(spec.get("license", "")),
            rate_rps=float(spec.get("rate_rps", 1.0) or 1.0),
            cs_authority=bool(spec.get("cs_authority", False)),
            notes=str(spec.get("notes", "")),
            requires_network=bool(spec.get("requires_network", True)),
            enabled=bool(spec.get("enabled", True)),
            disabled_reason=str(spec.get("disabled_reason", "")),
            config=spec,
        )
        super().__init__(**kw)

    def describe(self) -> dict[str, Any]:
        d = super().describe()
        d["declared_in_config"] = True
        return d


class GenericHttpChannel(_DeclaredChannel):
    """A REST channel described entirely by config."""

    def _render(self, template: str, argument: str) -> str:
        return template.replace("{query}", argument).replace("{id}", argument)

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        for hname, value in (self.decl.get("headers") or {}).items():
            headers[str(hname)] = self._render(str(value), "")
        auth = self.decl.get("auth", "none")
        if isinstance(auth, str) and auth.startswith("env:") and not auth.endswith("?"):
            var = auth[4:]
            secret = os.environ.get(var, "")
            if secret:
                header_name = str(self.decl.get("auth_header", "Authorization"))
                template = str(self.decl.get("auth_value", "Bearer {key}"))
                headers[header_name] = template.replace("{key}", secret)
        return headers

    def _params(self, extra: dict[str, Any]) -> dict[str, Any]:
        params: dict[str, Any] = dict(self.decl.get("params") or {})
        auth = self.decl.get("auth", "none")
        if isinstance(auth, str) and auth.startswith("env:") and not auth.endswith("?"):
            var = auth[4:]
            secret = os.environ.get(var, "")
            key_param = self.decl.get("auth_param")
            if secret and key_param:
                params[str(key_param)] = secret
        params.update(extra)
        return params

    def _run(self, argument: str, *, mode: str, limit: int,
             year_from: int | None = None, year_to: int | None = None) -> ChannelResult:
        url = self._render(str(self.decl.get("url", "")), argument)
        if not url:
            return ChannelResult(self.name, error="declared channel has no 'url'")
        extra: dict[str, Any] = {}
        limit_param = self.decl.get("limit_param")
        if limit_param:
            extra[str(limit_param)] = limit
        if mode == "search" and self.decl.get("query_param"):
            extra[str(self.decl["query_param"])] = argument
        if year_from and self.decl.get("year_from_param"):
            extra[str(self.decl["year_from_param"])] = year_from
        if year_to and self.decl.get("year_to_param"):
            extra[str(self.decl["year_to_param"])] = year_to
        data, resp, ev_id = self.request_json(
            url, params=self._params(extra), headers=self._headers(), notes=f"{self.name} {mode}"
        )
        res = ChannelResult(self.name, ev_id=ev_id, queries=[{"url": url, "params": extra}])
        if data is None:
            res.error = resp.error or f"HTTP {resp.status}"
            return res
        mapping = self.decl.get("map") or {}
        items_path = str(mapping.get("items", ""))
        items = _dig(data, items_path) if items_path else data
        if isinstance(items, dict):
            items = [items]
        if not isinstance(items, list):
            res.error = f"mapping 'items' path {items_path!r} did not yield a list"
            return res
        total_path = mapping.get("total")
        if total_path:
            total = _dig(data, str(total_path))
            if isinstance(total, (int, str)) and str(total).isdigit():
                res.total_available = int(total)
        for item in items[: max(1, limit * 3)]:
            rec = self._map_item(item, mapping, ev_id)
            if rec is None:
                continue
            if year_from and rec.year and rec.year < year_from:
                continue
            if year_to and rec.year and rec.year > year_to:
                continue
            res.records.append(rec)
            if len(res.records) >= limit:
                break
        return res

    def _map_item(self, item: Any, mapping: dict[str, Any], ev_id: str) -> ChannelRecord | None:
        def take(field: str) -> Any:
            path = mapping.get(field)
            return _dig(item, str(path)) if path else None

        title = str(take("title") or "").strip()
        if not title:
            return None
        authors: list[str] = []
        apath = mapping.get("authors")
        if apath:
            raw = _dig(item, str(apath))
            template = str(mapping.get("author_template", "{v}"))
            if isinstance(raw, list):
                for a in raw:
                    if isinstance(a, dict):
                        a = _dig(a, str(mapping.get("author_name", "name")))
                    if a:
                        authors.append(template.replace("{v}", str(a)).strip())
            elif raw:
                authors.append(str(raw))
        return ChannelRecord(
            channel=self.name,
            title=title,
            authors=authors,
            year=_as_int(take("year")),
            venue=str(take("venue") or ""),
            abstract=str(take("abstract") or ""),
            doi=str(take("doi") or ""),
            arxiv_id=str(take("arxiv_id") or ""),
            url=str(take("url") or ""),
            pdf_url=str(take("pdf_url") or ""),
            kind=str(mapping.get("kind", "record")),
            ev=ev_id,
            extras={"declared": True},
        )


class _ResponseExtractor:
    """Normalises assorted JSON envelopes into ChannelRecords.

    Shared by the CLI and MCP generic channels. It lives in its own mixin rather than in
    one of them because calling the other's unbound method is a real trap:
    ``OtherClass._extract(self, data, ...)`` binds the wrong object to the first
    parameter and silently shifts every argument, producing an empty result with no
    error at all — which is exactly how the MCP-source path failed before this existed.
    """

    def _extract(
        self,
        data: Any,
        res: ChannelResult,
        *,
        limit: int,
        mapping: dict[str, Any],
    ) -> None:
        """Normalise a tool's JSON into ChannelRecords.

        Accepts the common envelopes ``{papers|results|items|data|records: [...]}``, a
        bare list, and MCP's ``{content: [{text: "<json>"}]}``. Diagnostics found in an
        ``errors`` map become warnings, so a thin result set explains itself rather than
        looking like "nothing exists".
        """
        if isinstance(data, dict) and "content" in data and "papers" not in data:
            data = _unwrap_mcp_content(data)
        items: Any = data
        if isinstance(data, dict):
            found = False
            for key in ("papers", "results", "items", "data", "records"):
                if key not in data:
                    continue
                if isinstance(data[key], list):
                    items, found = data[key], True
                else:
                    # A known key holding the wrong type is a mapping problem worth
                    # naming, not a reason to report "no results".
                    res.error = (
                        f"tool returned {key!r} as {type(data[key]).__name__}, expected a list"
                    )
                    return
                break
            if not found:
                # An unrecognised envelope must be reported. Returning zero records with
                # no error is indistinguishable from "this source has nothing", which is
                # the silent-empty-result failure mode this tool exists to prevent.
                shape = ", ".join(sorted(data)[:8]) or "(empty object)"
                if isinstance(data.get("total"), int):
                    res.total_available = data["total"]
                res.error = (
                    "could not find a record list in the tool output; looked for "
                    f"papers/results/items/data/records, saw keys: {shape}"
                )
                return
            errors = data.get("errors")
            if isinstance(errors, dict):
                for src, msg in errors.items():
                    if msg:
                        res.warnings.append(f"{src}: {str(msg)[:200]}")
            if isinstance(data.get("total"), int):
                res.total_available = data["total"]
        if isinstance(items, dict):
            items = [items]
        if not isinstance(items, list):
            res.error = "tool output did not contain a list of records"
            return
        for item in items:
            if not isinstance(item, dict):
                continue
            rec = self._map_item(item, mapping, res.ev_id)
            if rec is None:
                continue
            res.records.append(rec)
            if len(res.records) >= limit:
                break

    def _map_item(
        self, item: dict[str, Any], mapping: dict[str, Any], ev_id: str
    ) -> "ChannelRecord | None":
        def pick(*names: str) -> Any:
            for n in names:
                path = mapping.get(n)
                if path:
                    v = _dig(item, str(path))
                    if v not in (None, ""):
                        return v
            for n in names:
                if n in item and item[n] not in (None, ""):
                    return item[n]
            return None

        title = str(pick("title") or "").strip()
        if not title:
            return None
        return ChannelRecord(
            channel=self.name,
            title=title,
            authors=_as_list(pick("authors")),
            year=_as_int(pick("year", "published_date", "published")),
            venue=str(pick("venue", "journal", "categories") or ""),
            abstract=str(pick("abstract", "summary") or ""),
            doi=str(pick("doi") or ""),
            arxiv_id=str(pick("arxiv_id", "arxiv") or ""),
            openreview_id=str(pick("openreview_id") or ""),
            pmid=str(pick("pmid") or ""),
            url=str(pick("url") or ""),
            pdf_url=str(pick("pdf_url", "pdf") or ""),
            kind=str(mapping.get("kind", "record")),
            ev=ev_id,
            extras={
                "channel_source": item.get("source", ""),
                "native_id": item.get("paper_id", "") or item.get("id", ""),
            },
        )


def _unwrap_mcp_content(data: dict[str, Any]) -> Any:
    """Extract the payload from an MCP tool result shaped {content: [{text: ...}]}."""
    content = data.get("content")
    if not isinstance(content, list):
        return data
    texts = [c.get("text", "") for c in content if isinstance(c, dict)]
    joined = "\n".join(t for t in texts if t)
    if not joined.strip():
        return data
    try:
        return json.loads(joined)
    except json.JSONDecodeError:
        return {"text": joined}


class GenericCliChannel(_ResponseExtractor, _DeclaredChannel):
    """Bridge to an installed command-line tool, parsing its JSON stdout.

    The local ``paper-search`` tool is wired this way: it already covers 21 sources,
    so re-implementing them would be wasteful, and shelling out keeps this project
    free of a hard dependency on it (if the tool is absent, the channel reports
    itself unavailable and everything else still works).
    """

    def available(self) -> tuple[bool, str]:
        usable, reason = super().available()
        if not usable:
            return usable, reason
        exe = str(self.decl.get("command", ""))
        if not exe:
            return False, "no command declared"
        resolved = _resolve_command(exe)
        if not resolved:
            return False, f"command not found on PATH: {exe}"
        return True, ""

    def _run(self, args: list[str], *, notes: str) -> tuple[Any | None, ChannelResult]:
        exe = str(self.decl.get("command", ""))
        resolved = _resolve_command(exe)
        res = ChannelResult(self.name, queries=[{"command": [exe] + args}])
        if not resolved:
            res.error = f"command not found: {exe}"
            return None, res
        env = dict(os.environ)
        # Several tools on Windows fail on non-ASCII output under the legacy code page;
        # force UTF-8 so a paper with accents or CJK in its title does not crash parsing.
        env.setdefault("PYTHONUTF8", "1")
        env.setdefault("PYTHONIOENCODING", "utf-8")
        timeout = float(self.decl.get("timeout", 180) or 180)
        try:
            proc = subprocess.run(
                [resolved] + args,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                env=env,
                shell=resolved.casefold().endswith((".cmd", ".bat")),
            )
        except subprocess.TimeoutExpired:
            res.error = f"command timed out after {timeout:.0f}s"
            self.snapshot(command=[resolved] + args, error=res.error, notes=notes)
            return None, res
        except OSError as exc:
            res.error = f"could not run command: {exc}"
            self.snapshot(command=[resolved] + args, error=res.error, notes=notes)
            return None, res
        ev_id = self.snapshot(
            command=[resolved] + args,
            body=proc.stdout or "",
            status=proc.returncode,
            error="" if proc.returncode == 0 else (proc.stderr or "")[:500],
            notes=notes,
        )
        res.ev_id = ev_id
        if proc.returncode != 0 and not (proc.stdout or "").strip():
            res.error = (proc.stderr or f"exit code {proc.returncode}").strip()[:400]
            return None, res
        try:
            return json.loads(proc.stdout), res
        except json.JSONDecodeError as exc:
            res.error = f"command did not emit JSON: {exc}"
            return None, res

    def search(
        self,
        query: str,
        *,
        limit: int = 10,
        year_from: int | None = None,
        year_to: int | None = None,
        **kw: Any,
    ) -> ChannelResult:
        args = [str(a) for a in (self.decl.get("search_args") or ["search"])]
        args.append(query)
        limit_flag = self.decl.get("limit_flag")
        if limit_flag:
            args += [str(limit_flag), str(limit)]
        sources_flag = self.decl.get("sources_flag")
        if sources_flag and self.decl.get("sources"):
            args += [str(sources_flag), str(self.decl["sources"])]
        year_flag = self.decl.get("year_flag")
        if year_flag and (year_from or year_to):
            args += [str(year_flag), f"{year_from or ''}-{year_to or ''}"]
        data, res = self._run(args, notes=f"{self.name} search")
        if data is None:
            return res
        self._extract(data, res, limit=limit, mapping=self.decl.get("map") or {})
        return res

    def lookup(self, identifier: str, **kw: Any) -> ChannelResult:
        args = [str(a) for a in (self.decl.get("lookup_args") or [])]
        if not args:
            return ChannelResult(self.name, error="no lookup_args declared")
        args.append(identifier)
        data, res = self._run(args, notes=f"{self.name} lookup")
        if data is None:
            return res
        self._extract(data, res, limit=5, mapping=self.decl.get("map") or {})
        return res

    def download_pdf(self, rec: ChannelRecord, **kw: Any) -> tuple[bytes, str, str]:
        """Delegate PDF fetching to the CLI when it declares a download subcommand."""
        dl = self.decl.get("download_args")
        if not dl:
            return super().download_pdf(rec, **kw)
        native = rec.extras.get("native_id") or rec.arxiv_id or rec.doi
        src = rec.extras.get("channel_source") or rec.channel
        if not native:
            return b"", "", "record has no native id for the CLI downloader"
        outdir = kw.get("outdir")
        args = [str(a) for a in dl] + [str(src), str(native)]
        out_flag = self.decl.get("output_flag")
        if outdir and out_flag:
            args += [str(out_flag), str(outdir)]
        data, res = self._run(args, notes=f"{self.name} download")
        if data is None:
            return b"", "", res.error
        path = ""
        if isinstance(data, dict):
            path = str(data.get("path") or data.get("file") or "")
        if not path:
            return b"", "", "CLI downloader did not report a file path"
        try:
            with open(path, "rb") as fh:
                return fh.read(), path, ""
        except OSError as exc:
            return b"", path, f"could not read downloaded file: {exc}"


class GenericMcpChannel(_ResponseExtractor, _DeclaredChannel):
    """Call a Model Context Protocol server over stdio.

    Implemented against the minimal JSON-RPC framing (one JSON object per line,
    ``initialize`` -> ``tools/call``) rather than pulling in an MCP SDK, so a
    user-configured MCP server remains an *option* rather than a dependency.
    """

    def available(self) -> tuple[bool, str]:
        usable, reason = super().available()
        if not usable:
            return usable, reason
        cmd = self.decl.get("command")
        if not cmd:
            return False, "no MCP command declared"
        exe = cmd[0] if isinstance(cmd, list) else str(cmd)
        if not _resolve_command(exe):
            return False, f"MCP server command not found: {exe}"
        return True, ""

    def _call_tool(self, tool: str, arguments: dict[str, Any]) -> tuple[Any | None, ChannelResult]:
        res = ChannelResult(self.name, queries=[{"mcp_tool": tool, "arguments": arguments}])
        cmd = self.decl.get("command")
        argv = cmd if isinstance(cmd, list) else shlex.split(str(cmd))
        timeout = float(self.decl.get("timeout", 120) or 120)
        env = dict(os.environ)
        env.setdefault("PYTHONUTF8", "1")
        try:
            proc = subprocess.Popen(
                argv,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
                bufsize=1,
            )
        except OSError as exc:
            res.error = f"could not start MCP server: {exc}"
            return None, res
        messages = [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "ccb", "version": "0.1"},
                },
            },
            {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": tool, "arguments": arguments},
            },
        ]
        payload = "".join(json.dumps(m) + "\n" for m in messages)
        try:
            out, err = proc.communicate(payload, timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            res.error = f"MCP call timed out after {timeout:.0f}s"
            return None, res
        ev_id = self.snapshot(
            body=out or "", status=proc.returncode or 0, error=(err or "")[:400],
            notes=f"mcp {tool}",
        )
        res.ev_id = ev_id
        response = None
        for line in (out or "").splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if msg.get("id") == 2:
                response = msg
        if response is None:
            res.error = f"MCP server returned no result for tool {tool!r}: {(err or '')[:200]}"
            return None, res
        if "error" in response:
            res.error = f"MCP error: {str(response['error'])[:300]}"
            return None, res
        content = (response.get("result") or {}).get("content")
        if isinstance(content, list):
            texts = [c.get("text", "") for c in content if isinstance(c, dict)]
            joined = "\n".join(t for t in texts if t)
            try:
                return json.loads(joined), res
            except json.JSONDecodeError:
                return {"text": joined}, res
        return response.get("result"), res

    def search(self, query: str, *, limit: int = 10, **kw: Any) -> ChannelResult:
        tool = str(self.decl.get("search_tool", "search"))
        args = dict(self.decl.get("search_arguments") or {})
        args[str(self.decl.get("query_arg", "query"))] = query
        args[str(self.decl.get("limit_arg", "limit"))] = limit
        data, res = self._call_tool(tool, args)
        if data is None:
            return res
        self._extract(data, res, limit=limit, mapping=self.decl.get("map") or {})
        return res

    def lookup(self, identifier: str, **kw: Any) -> ChannelResult:
        tool = str(self.decl.get("lookup_tool", ""))
        if not tool:
            return ChannelResult(self.name, error="no lookup_tool declared")
        args = dict(self.decl.get("lookup_arguments") or {})
        args[str(self.decl.get("id_arg", "id"))] = identifier
        data, res = self._call_tool(tool, args)
        if data is None:
            return res
        self._extract(data, res, limit=5, mapping=self.decl.get("map") or {})
        return res


def _resolve_command(exe: str) -> str:
    """Locate an executable: absolute path, or search PATH (Windows-aware)."""
    if not exe:
        return ""
    if os.path.isabs(exe) and os.path.exists(exe):
        return exe
    from shutil import which

    found = which(exe)
    if found:
        return found
    if sys.platform == "win32" and not exe.casefold().endswith((".cmd", ".bat", ".exe")):
        for ext in (".cmd", ".bat", ".exe"):
            found = which(exe + ext)
            if found:
                return found
    return ""

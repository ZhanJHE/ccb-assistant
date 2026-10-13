"""Channel registry — discovery, capability routing and health.

Centralises three things the aggregator needs so no caller has to know them:

* **what exists** — built-in channels plus any declared in ``<library>/channels.yaml``
  or ``$CCB_CHANNELS``, so adding a source is configuration, not code;
* **who can do the job** — capability-based routing (search / lookup / pdf / oa_resolve)
  with CS-authority preference;
* **who is actually usable right now** — a missing credential or a gated source is
  reported as an unavailable channel with a reason, never as an empty result.
"""

from __future__ import annotations

import importlib
from dataclasses import replace
from pathlib import Path
from typing import Any, Iterable

from ...library.evidence import EvidenceStore
from ..net import Http, credential
from .base import Channel

# name -> "module:ClassName". Adding a built-in channel is one line here plus the module.
BUILTIN_CHANNELS: dict[str, str] = {
    "crossref": "crossref:CrossrefChannel",
    "openalex": "openalex:OpenAlexChannel",
    "openreview": "openreview:OpenReviewChannel",
    "arxiv": "arxiv:ArxivChannel",
    "dblp": "dblp:DblpChannel",
    "europepmc": "europepmc:EuropePmcChannel",
    "paper_search": "paper_search:PaperSearchChannel",
}


def _gap(var: str, kind: str, effect: str) -> dict[str, str]:
    """One missing credential, described in terms a user can act on."""
    from ..net import CREDENTIAL_NOTES

    entry = {"var": var, "kind": kind, "effect": effect}
    if var in CREDENTIAL_NOTES:
        entry["note"] = CREDENTIAL_NOTES[var]
    return entry

# Default health, learned from live probing rather than from documentation. Used to
# explain a degradation before the first call, and corrected by runtime results.
KNOWN_HEALTH: dict[str, dict[str, str]] = {
    "dblp": {
        "status": "gated",
        "note": "Anubis anti-bot challenge answers HTTP 200 with an HTML page; expect "
                "degradation and let other channels carry the query.",
    },
    "paper_search": {
        "status": "ok",
        "note": "Local 21-source CLI bridge; no MCP required, invoked through the shell.",
    },
}


class Registry:
    """Holds channel instances and answers routing questions about them."""

    def __init__(
        self,
        *,
        http: Http | None = None,
        evidence: EvidenceStore | None = None,
        verbose: bool = False,
        config_paths: Iterable[Path] | None = None,
        enabled: Iterable[str] | None = None,
        disabled: Iterable[str] | None = None,
        validators_path: Path | None = None,
    ):
        self.verbose = verbose
        # One shared transport, with per-host rate limits taken from each channel's
        # declaration and the union of their opt-in retry codes. Sharing the client is
        # what makes politeness to a host actually hold across channels that use it.
        #
        # The rate table is keyed by the *hosts a channel requests*, because that is what
        # the token bucket is handed: a table keyed by channel name never matched a
        # netloc, so every host silently got `default_rps` and arXiv's declared 3s/request
        # was really 1 req/s.
        if http is None:
            retry: set[int] = set()
            for target in BUILTIN_CHANNELS.values():
                mod_name, _, cls_name = target.partition(":")
                try:
                    module = importlib.import_module(f"..channels.{mod_name}", __package__)
                    cls = getattr(module, cls_name)
                except Exception:
                    continue
                retry |= set(getattr(cls, "extra_retry_codes", ()) or ())
            http = Http(
                extra_retry_on=tuple(sorted(retry)),
                validators_path=validators_path,
            )
        self.http = http
        self.evidence = evidence
        self._channels: dict[str, Channel] = {}
        self._enabled = {s.casefold() for s in enabled} if enabled else None
        self._disabled = {s.casefold() for s in (disabled or [])}
        self._config: dict[str, dict[str, Any]] = {}
        self._load_config(config_paths or [])
        self._load_builtins()
        self._load_declared()

    # ------------------------------------------------------------------ #
    # Construction
    # ------------------------------------------------------------------ #

    def _register_rates(self, spec: Any) -> None:
        """Fold a channel's declared rate into the shared per-host table.

        The strictest declared rate wins when two channels share a host: being slower than
        necessary is a cost, being faster than a source asked for is a violation.
        """
        rate = float(getattr(spec, "rate_rps", 1.0) or 1.0)
        for host in getattr(spec, "hosts", ()) or ():
            host = str(host).strip().casefold()
            if not host:
                continue
            current = self.http.host_rates.get(host)
            self.http.host_rates[host] = rate if current is None else min(current, rate)

    def _load_config(self, paths: Iterable[Path]) -> None:
        """Read channel declarations from YAML/JSON files (best effort)."""
        for path in paths:
            p = Path(path)
            if not p.exists():
                continue
            data: Any = None
            try:
                text = p.read_text(encoding="utf-8")
                if p.suffix.casefold() in (".yaml", ".yml"):
                    import yaml  # optional dependency, only for config files

                    data = yaml.safe_load(text)
                else:
                    import json

                    data = json.loads(text)
            except Exception:
                continue
            if isinstance(data, dict):
                for name, spec in (data.get("channels") or {}).items():
                    if isinstance(spec, dict):
                        self._config[str(name)] = spec

    def _load_builtins(self) -> None:
        for name, target in BUILTIN_CHANNELS.items():
            if name in self._disabled:
                continue
            if self._enabled is not None and name.casefold() not in self._enabled:
                continue
            mod_name, _, cls_name = target.partition(":")
            try:
                module = importlib.import_module(f"..channels.{mod_name}", __package__)
                cls = getattr(module, cls_name)
            except Exception:
                # A broken optional channel must never prevent the tool from running.
                continue
            try:
                chan = cls(http=self.http, evidence=self.evidence, verbose=self.verbose)
            except Exception:
                continue
            self._apply_config(chan)
            self._register_rates(chan.spec)
            self._channels[name] = chan

    def _load_declared(self) -> None:
        """Instantiate channels declared only in config, without a Python module.

        This is how a keyed or MCP-backed source is added without touching code: the
        declaration supplies the endpoint and the credential variable, and the generic
        handler does the rest.
        """
        from .generic import GenericHttpChannel, GenericCliChannel, GenericMcpChannel

        for name, spec in self._config.items():
            if name in self._channels or name in self._disabled:
                continue
            kind = str(spec.get("kind", "http")).casefold()
            try:
                if kind == "http":
                    chan: Channel = GenericHttpChannel(name, spec, http=self.http,
                                                       evidence=self.evidence)
                elif kind == "cli":
                    chan = GenericCliChannel(name, spec, evidence=self.evidence)
                elif kind == "mcp":
                    chan = GenericMcpChannel(name, spec, evidence=self.evidence)
                else:
                    continue
            except Exception:
                continue
            self._register_rates(chan.spec)
            self._channels[name] = chan

    def _apply_config(self, chan: Channel) -> None:
        """Apply a config override to *this instance's* spec.

        `spec` is a class attribute on every built-in channel, so assigning to
        `chan.spec.rate_rps` rewrote shared class state: a second Registry built for
        another library in the same process inherited the override, and `describe()`
        reported the injected value as if the channel had declared it.
        """
        override = self._config.get(chan.name)
        if not override:
            return
        changes: dict[str, Any] = {}
        if "enabled" in override:
            changes["enabled"] = bool(override["enabled"])
            if not changes["enabled"]:
                changes["disabled_reason"] = str(
                    override.get("disabled_reason", "disabled in config")
                )
        if "rate_rps" in override:
            try:
                changes["rate_rps"] = float(override["rate_rps"])
            except (TypeError, ValueError):
                pass
        if changes:
            chan.spec = replace(chan.spec, **changes)

    # ------------------------------------------------------------------ #
    # Access
    # ------------------------------------------------------------------ #

    def names(self) -> list[str]:
        return sorted(self._channels)

    def get(self, name: str) -> Channel | None:
        return self._channels.get(name)

    def all(self) -> list[Channel]:
        return [self._channels[n] for n in self.names()]

    def usable(self, cap: str = "") -> list[Channel]:
        out = []
        for chan in self.all():
            ok, _ = chan.available()
            if ok and (not cap or chan.has(cap)):
                out.append(chan)
        return out

    def search_channels(self, spec: str = "") -> list[Channel]:
        """Resolve a user/channel selector into concrete channels.

        Accepts "auto" (all search-capable usable channels, CS authorities first),
        "all", or a comma-separated list of names. Unknown names are ignored rather
        than fatal, so a typo degrades to "fewer channels" and is reported.
        """
        selector = (spec or "auto").strip()
        if selector.casefold() in ("auto", ""):
            chans = self.usable("search")
            return sorted(
                chans,
                key=lambda c: (0 if c.spec.cs_authority else 1, c.spec.name),
            )
        if selector.casefold() == "all":
            return self.usable("search")
        wanted = [s.strip().casefold() for s in selector.split(",") if s.strip()]
        out = [self._channels[n] for n in self.names() if n.casefold() in wanted]
        return out

    def unknown_names(self, spec: str) -> list[str]:
        if not spec or spec.casefold() in ("auto", "all"):
            return []
        known = {n.casefold() for n in self.names()}
        return [s.strip() for s in spec.split(",") if s.strip() and s.strip().casefold() not in known]

    # ------------------------------------------------------------------ #
    # Reporting
    # ------------------------------------------------------------------ #

    def report(self) -> list[dict[str, Any]]:
        """Per-channel availability, with credential state and no secret values."""
        out: list[dict[str, Any]] = []
        for chan in self.all():
            d = chan.describe()
            health = KNOWN_HEALTH.get(chan.name)
            if health:
                d["health"] = health["status"]
                d["health_note"] = health["note"]
            out.append(d)
        return out

    def availability_summary(self) -> dict[str, Any]:
        """Per-channel availability plus credential state, with no secret values.

        Also reports a credential that is configured but whose channel is
        not loaded. That case is otherwise invisible — the user believes a source is
        enabled and nothing says otherwise — so it is surfaced as a configuration note
        rather than silently ignored.
        """
        from ..net import KNOWN_CREDENTIALS, credential_provider

        usable = [c.name for c in self.all() if c.available()[0]]
        unusable = {c.name: c.available()[1] for c in self.all() if not c.available()[0]}
        present = sorted(
            {
                var
                for c in self.all()
                for var in c.spec.required_credentials() + c.spec.optional_credentials()
                if credential(var)
            }
        )
        # What is missing, and what it costs. A caller that only learns "this channel is
        # unavailable" cannot tell the user whether to go and find a key or to carry on
        # without one; `kind` and `effect` answer exactly that, and `note` covers the
        # cases where the answer is not implied by the channel's declaration.
        missing: dict[str, list[dict[str, str]]] = {}
        for c in self.all():
            gaps: list[dict[str, str]] = []
            for var in c.spec.required_credentials():
                if not credential(var):
                    gaps.append(_gap(var, "required",
                                     "the channel cannot be used without it"))
            for var in c.spec.optional_credentials():
                if not credential(var):
                    gaps.append(_gap(var, "optional", "raises rate limits only"))
            if gaps:
                missing[c.name] = gaps

        loaded = {c.name for c in self.all()}
        orphaned = {
            var: credential_provider(var)
            for var in sorted(KNOWN_CREDENTIALS)
            if credential(var) and credential_provider(var) not in loaded
        }
        out: dict[str, Any] = {
            "usable": usable,
            "unavailable": unusable,
            "credentials_present": present,
            "credentials_missing": missing,
            "credential_guidance": (
                "Never move a credential value through a conversation, a log or a command "
                "line. Tell the user which environment variable enables the source and "
                "what it buys, ask them to set it in their own environment, then re-run "
                "the command. Credential values are never read into output."
            ),
        }
        if orphaned:
            out["credentials_without_channel"] = orphaned
            out["credentials_without_channel_note"] = (
                "These credentials are set but the channel that consumes them is not "
                "loaded, so the source is not being used. Enable the channel (add it to "
                "the registry or a channels.yaml declaration) to take advantage of it."
            )
        return out

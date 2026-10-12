"""The topics command surface, as pure functions.

Kept out of ``cli.py`` so the topics module never has to import the CLI (which would
close a cycle) and so the behaviour can be exercised without an argument parser. Each
entry point takes the library, a resolver that may be ``None`` when offline, and a
plain settings mapping, and returns a payload. Exit codes are the CLI's business.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from . import candidates as candidates_mod
from . import ccf as ccf_mod
from . import draft as draft_mod
from . import gaps as gaps_mod
from . import operators as operators_mod
from . import rating as rating_mod
from . import store as store_mod
from . import survey as survey_mod

if TYPE_CHECKING:  # pragma: no cover - import cycle guard
    from ..library.store import Library
    from ..search.acquire import Resolver

ACTIONS = (
    "survey",
    "gaps",
    "candidates",
    "draft",
    "rate",
    "save",
    "list",
    "show",
    "venues",
    "operators",
)


def _opt(value: Any, default: Any) -> Any:
    return default if value is None else value


def run(
    action: str,
    library: "Library",
    resolver: "Resolver | None",
    args: Any,
) -> dict[str, Any]:
    """Execute one topics action and return its payload."""
    if action == "survey":
        result = survey_mod.survey(
            library,
            str(args.query),
            resolver=resolver,
            offline=bool(getattr(args, "offline", False)),
            min_works=int(_opt(getattr(args, "min_works", None), survey_mod.DEFAULT_MIN_WORKS)),
            min_fulltext=int(
                _opt(getattr(args, "min_fulltext", None), survey_mod.DEFAULT_MIN_FULLTEXT)
            ),
            year_from=getattr(args, "year_from", None),
            year_to=getattr(args, "year_to", None),
            limit=int(_opt(getattr(args, "limit", None), survey_mod.DEFAULT_LIMIT)),
            top_terms=int(_opt(getattr(args, "top_terms", None), 40)),
            max_n=int(_opt(getattr(args, "max_n", None), 2)),
        )
        if not result.get("error"):
            survey_mod.save_survey(library, result)
        return result

    if action == "gaps":
        return gaps_mod.gaps(
            library,
            str(args.survey_id),
            max_per_work=int(_opt(getattr(args, "max_per_work", None), 3)),
            limit=int(_opt(getattr(args, "limit", None), 60)),
        )

    if action == "candidates":
        result = candidates_mod.build(
            library,
            str(args.survey_id),
            limit=int(_opt(getattr(args, "limit", None), 25)),
            per_kind=int(_opt(getattr(args, "per_kind", None), 15)),
            include_mined=bool(getattr(args, "include_mined", False)),
            self_check=not bool(getattr(args, "no_self_check", False)),
        )
        if not result.get("error"):
            candidates_mod.save_candidates(library, result)
        return result

    if action == "draft":
        return draft_mod.draft(library, str(args.candidate_id))

    if action == "rate":
        return rating_mod.rate_and_store(
            library, str(args.topic_id), target_venue=str(getattr(args, "venue", "") or "")
        )

    if action == "save":
        return _save(library, str(args.topic_id))

    if action == "list":
        topics = store_mod.list_topics(
            library, limit=int(_opt(getattr(args, "limit", None), 0))
        )
        return {
            "topics": topics,
            "count": len(topics),
            "mined_keys": len(store_mod.mined_keys(library)),
            "note": (
                "Each entry consumed a (gap evidence x operator) key, so that combination "
                "will not be proposed again by `ccb topics candidates`."
            ),
        }

    if action == "show":
        record = store_mod.load_json(library, "records", str(args.topic_id))
        if record is None:
            return {
                "error": "unknown_topic",
                "topic_id": str(args.topic_id),
                "message": "No stored topic with that id. Run `ccb topics list` to see them.",
            }
        markdown = draft_mod.render_markdown(record)
        payload = dict(record)
        if getattr(args, "markdown", False):
            payload = {"topic_id": record.get("topic_id", ""), "markdown": markdown}
        else:
            payload["markdown_path"] = str(
                store_mod.artefact_path(library, "drafts", str(args.topic_id), suffix=".md")
            )
        return payload

    if action == "venues":
        catalog = ccf_mod.default_catalog()
        if getattr(args, "verify", False):
            return catalog.verify()
        query = str(getattr(args, "query", "") or "")
        rows = catalog.search(query, limit=int(_opt(getattr(args, "limit", None), 20)))
        return {
            "query": query,
            "venues": [v.as_dict() for v in rows],
            "count": len(rows),
            "catalog": catalog.stats(),
            "note": (
                "A venue absent from this catalogue is reported as unmatched rather than "
                "given a guessed rank. Set CCB_CCF_CATALOG to replace the bundled subset."
            ),
        }

    if action == "operators":
        return {
            "operators": operators_mod.catalog(),
            "novelty_types": list(operators_mod.NOVELTY_TYPES),
            "difficulty_scale": {
                "min": operators_mod._MIN_DIFFICULTY,
                "max": operators_mod._MAX_DIFFICULTY,
                "note": "2 = apply an existing method; 5 = a new framework, bound or mechanism",
            },
        }

    return {"error": "unknown_action", "action": action}


def _save(library: "Library", topic_id: str) -> dict[str, Any]:
    """Commit a drafted topic: export the Markdown and retire its de-duplication key."""
    from ..core.util import utc_now

    record = store_mod.load_json(library, "records", topic_id)
    if record is None:
        return {
            "error": "unknown_topic",
            "topic_id": topic_id,
            "message": "No stored topic with that id. Run `ccb topics draft <candidate_id>` first.",
        }
    warnings: list[str] = []
    if not record.get("rating"):
        warnings.append(
            "No CCF estimate is recorded yet; run `ccb topics rate <topic_id>` so the "
            "saved draft states its basis."
        )
    record["status"] = "committed"
    record["committed_at"] = utc_now()
    markdown = draft_mod.render_markdown(record)
    draft_path = store_mod.save_text(library, "drafts", topic_id, markdown)
    record["markdown_path"] = str(draft_path)
    store_mod.save_json(library, "records", topic_id, record)
    store_mod.remember_topic(library, record)
    payload: dict[str, Any] = {
        "topic_id": topic_id,
        "status": record["status"],
        "title": record.get("title_hint", ""),
        "estimated_ccf": (record.get("rating") or {}).get("estimated_ccf", ""),
        "markdown_path": str(draft_path),
        "dedup_keys": record.get("dedup_keys", []),
        "message": (
            f"Committed. The draft is at {draft_path}. Its "
            f"{len(record.get('dedup_keys', []))} de-duplication key(s) are now retired, so "
            f"this combination will not be proposed again."
        ),
    }
    if warnings:
        payload["warnings"] = warnings
    return payload

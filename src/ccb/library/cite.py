"""Citation export.

Two rules drive this whole module:

1. **Never invent a field.** A missing volume or page range is omitted, not guessed
   and not filled from a different paper's record. Every source of every field is
   already recorded in the library, so an absent field is a fact about the metadata,
   not a gap to paper over.
2. **Stable keys.** Citation keys must not change between exports of the same record,
   or a manuscript's \\cite commands break on re-export. Keys derive from the resolved
   author/year and a short hash of the work identity, never from list position.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

from ..core.model import WorkRecord
from ..core.util import normalize_title, slugify

# Venue name fragments -> BibTeX entry type. Journal-like by default, because an
# unpublished-looking record is more often a journal article than a conference paper.
_CONFERENCE_HINTS = (
    "conference", "proceedings", "workshop", "symposium", "neurips", "nips", "icml",
    "iclr", "acl", "emnlp", "naacl", "cvpr", "iccv", "eccv", "aaai", "ijcai", "kdd",
    "sigir", "www", "wsdm", "cikm", "icde", "sigmod", "vldb", "uss", "ccs", "sp",
    "oakland", "ndss", "mlsys", "colm", "tacl", "eacl", "coling", "ismir", "uist",
    "chi", "icra", "iros", "rss", "corl", "miccai", "recomb", "psb",
)
_WORKSHOP_HINTS = ("workshop", "tutorial", "demo", "poster", "extended abstract")
_PREPRINT_HINTS = ("arxiv", "biorxiv", "medrxiv", "ssrn", "preprint", "openreview")


def bibtex_type(work: WorkRecord) -> str:
    venue = (work.venue() or "").casefold()
    kind_hint = ""
    for m in work.manifestations:
        if m.kind:
            kind_hint = m.kind.casefold()
            break
    if any(h in venue for h in _PREPRINT_HINTS) or kind_hint == "preprint":
        return "misc" if kind_hint != "preprint" else "article"
    if any(h in venue for h in _WORKSHOP_HINTS):
        return "inproceedings"
    if any(h in venue for h in _CONFERENCE_HINTS) or kind_hint == "proceedings":
        return "inproceedings"
    if kind_hint == "journal":
        return "article"
    return "article" if work.venue() else "misc"


def author_list(work: WorkRecord, *, max_authors: int = 0) -> list[str]:
    return work.authors() if not max_authors else work.authors()[:max_authors]


def citation_key(work: WorkRecord, *, style: str = "authorYear") -> str:
    """Deterministic key. Falls back to the identity hash, never to a counter."""
    authors = work.authors()
    year = work.year() or "n.d."
    if style == "hash":
        return "ccb" + re.sub(r"[^a-z0-9]", "", work.work_id)[:12]
    if style == "key":
        # Prefer a human-meaningful slice of the strongest identifier.
        for scheme in ("doi", "arxiv", "openreview", "dblp"):
            if work.ids.get(scheme):
                return f"{scheme}{re.sub(r'[^A-Za-z0-9]', '', work.ids[scheme])[:16]}"
    if not authors:
        return f"anon{year}{_key_suffix(work)}"
    from ..core.util import normalize_person

    last = normalize_person(authors[0]).split("|")[0] or "anon"
    last = re.sub(r"[^A-Za-z]", "", last) or "anon"
    if len(authors) == 1:
        return f"{last}{year}"
    if len(authors) <= 3:
        others = [normalize_person(a).split("|")[0] or "" for a in authors[1:]]
        initials = "".join(re.sub(r"[^A-Za-z]", "", o)[:1] for o in others)
        return f"{last}{initials}{year}"
    return f"{last}EtAl{year}"


def _key_suffix(work: WorkRecord) -> str:
    body = normalize_title(work.title())[:40]
    return slugify(body, maxlen=8)


def _bibtex_escape(value: str) -> str:
    """Escape for BibTeX without destroying Unicode.

    Braces are balanced (an unbalanced brace breaks compilation) and bare ``&``/``%``
    are escaped; accents are left as Unicode because modern engines (biber, XeLaTeX)
    handle them, and mangling them is worse than leaving them.
    """
    out = (value or "").replace("\\", "\\textbackslash{}")
    out = out.replace("&", "\\&").replace("%", "\\%").replace("#", "\\#")
    out = out.replace("_", "\\_")
    opens = out.count("{")
    closes = out.count("}")
    if opens > closes:
        out += "}" * (opens - closes)
    elif closes > opens:
        out = "{" * (closes - opens) + out
    return out.replace("\n", " ").strip()


def _field(name: str, value: Any) -> str:
    if value in (None, "", [], 0):
        return ""
    if isinstance(value, list):
        value = " and ".join(str(v) for v in value)
    return f"  {name} = {{{_bibtex_escape(str(value))}}}"


def to_bibtex(work: WorkRecord, *, key_style: str = "authorYear", include_notes: bool = False) -> str:
    """Render one BibTeX entry from resolved values only."""
    if work is None:
        return ""
    entry_type = bibtex_type(work)
    key = citation_key(work, style=key_style)
    venue = work.venue()
    fields: list[str] = []
    fields.append(_field("title", work.title()))
    authors = author_list(work)
    if authors:
        fields.append(_field("author", authors))
    fields.append(_field("year", work.year()))
    if venue:
        if entry_type == "inproceedings":
            fields.append(_field("booktitle", venue))
        elif entry_type == "article":
            fields.append(_field("journal", venue))
        else:
            fields.append(_field("howpublished", venue))
    # Volume/issue/pages come from claims so their origin is inspectable.
    from ..core.model import resolve_field

    for bib_name, claim_name in (
        ("volume", "volume"),
        ("number", "issue"),
        ("pages", "pages"),
        ("publisher", "publisher"),
    ):
        val = resolve_field(work.claims, claim_name)
        if val:
            fields.append(_field(bib_name, val))
    doi = work.ids.get("doi", "")
    if doi:
        fields.append(_field("doi", doi))
    # A URL only when it adds information beyond the DOI.
    url_claim = resolve_field(work.claims, "url")
    if url_claim and not doi:
        fields.append(_field("url", url_claim))
    arxiv = work.ids.get("arxiv", "")
    orid = work.ids.get("openreview", "")
    if arxiv:
        fields.append(_field("eprint", arxiv))
        fields.append(_field("archivePrefix", "arXiv"))
    if orid:
        fields.append(_field("note", f"OpenReview: {orid}"))
    if include_notes and not fields:
        fields.append(f"  note = {{ccb work_id {work.work_id}}}")
    body = ",\n".join(f for f in fields if f)
    return f"@{entry_type}{{{key},\n{body}\n}}"


def to_ris(work: WorkRecord) -> str:
    """RIS export, for reference managers. One record, TY..ER delimited."""
    ty = "CONF" if bibtex_type(work) == "inproceedings" else "JOUR"
    if not work.venue():
        ty = "GEN"
    lines = [f"TY  - {ty}"]
    for a in work.authors():
        lines.append(f"AU  - {a}")
    lines.append(f"TI  - {work.title()}")
    if work.year():
        lines.append(f"PY  - {work.year()}")
    if work.venue():
        lines.append(f"JO  - {work.venue()}")
    from ..core.model import resolve_field

    for tag, name in (("VL", "volume"), ("IS", "issue"), ("SP", "pages"),
                      ("PB", "publisher"), ("AB", "abstract")):
        val = resolve_field(work.claims, name)
        if val:
            lines.append(f"{tag}  - {val}")
    if work.ids.get("doi"):
        lines.append(f"DO  - {work.ids['doi']}")
    if work.ids.get("arxiv"):
        lines.append(f"AN  - arXiv:{work.ids['arxiv']}")
    if work.ids.get("openreview"):
        lines.append(f"AN  - OpenReview:{work.ids['openreview']}")
    url = resolve_field(work.claims, "url")
    if url:
        lines.append(f"UR  - {url}")
    lines.append("ER  - ")
    return "\n".join(lines)


def to_csl_json(work: WorkRecord) -> dict[str, Any]:
    """A minimal CSL-JSON item, so the library can feed citation processors."""
    from ..core.model import resolve_field

    item: dict[str, Any] = {
        "id": work.work_id,
        "type": "paper-conference" if bibtex_type(work) == "inproceedings" else "article-journal",
        "title": work.title(),
    }
    if work.authors():
        item["author"] = [_split_name(a) for a in work.authors()]
    if work.year():
        item["issued"] = {"date-parts": [[work.year()]]}
    if work.venue():
        key = "container-title"
        item[key] = work.venue()
    for csl, name in (("volume", "volume"), ("issue", "issue"), ("page", "pages"),
                      ("publisher", "publisher"), ("abstract", "abstract")):
        val = resolve_field(work.claims, name)
        if val:
            item[csl] = val
    if work.ids.get("doi"):
        item["DOI"] = work.ids["doi"]
    if work.ids.get("arxiv"):
        item["arXiv"] = work.ids["arxiv"]
    url = resolve_field(work.claims, "url")
    if url:
        item["URL"] = url
    return item


def _split_name(full: str) -> dict[str, str]:
    """Best-effort split of "Given Family" or "Family, Given" for CSL."""
    raw = (full or "").strip()
    if not raw:
        return {"literal": ""}
    if "," in raw:
        family, _, given = raw.partition(",")
        out = {"family": family.strip()}
        if given.strip():
            out["given"] = given.strip()
        return out
    parts = raw.split()
    if len(parts) == 1:
        return {"literal": raw}
    return {"family": parts[-1], "given": " ".join(parts[:-1])}


def export(
    works: Iterable[WorkRecord],
    *,
    fmt: str = "bibtex",
    key_style: str = "authorYear",
) -> str:
    """Render many works in one format. Unknown formats raise rather than guess."""
    fmt = (fmt or "bibtex").casefold()
    items = [w for w in works if w is not None]
    if fmt in ("bibtex", "bib", "b"):
        return "\n\n".join(to_bibtex(w, key_style=key_style) for w in items) + (
            "\n" if items else ""
        )
    if fmt == "ris":
        return "\n".join(to_ris(w) for w in items)
    if fmt in ("csl", "csl-json", "json"):
        import json

        return json.dumps([to_csl_json(w) for w in items], ensure_ascii=False, indent=2)
    if fmt in ("text", "txt", "plain"):
        return "\n".join(_plain(w) for w in items)
    raise ValueError(f"unsupported export format: {fmt!r} (bibtex, ris, csl, text)")


def _plain(work: WorkRecord) -> str:
    authors = work.authors()
    author_str = ", ".join(authors[:6]) + (" et al." if len(authors) > 6 else "")
    bits = [f"{author_str} ({work.year()}). {work.title()}."]
    if work.venue():
        bits.append(f"{work.venue()}.")
    if work.ids.get("doi"):
        bits.append(f"https://doi.org/{work.ids['doi']}")
    return " ".join(b for b in bits if b)

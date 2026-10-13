"""One-shot migration: 论文学习/文献索引.md → ccb papers/ library.

Parses the markdown index (15 topics, ~775 entries), supplements with abstracts from
论文数据库/papers.json, upserts each entry as a WorkRecord (identity chain, dedup and
provenance come for free), and attaches the local PDFs. Then copies the topic surveys
to docs/调研/.

Run once; delete after.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SRC = Path(r"C:\Users\ZhanJH\Desktop\论文学习")
INDEX = SRC / "文献索引.md"
PAPERS_JSON = SRC / "论文数据库" / "papers.json"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from ccb.core.model import ChannelRecord  # noqa: E402
from ccb.library import Library  # noqa: E402

# The index table has 9 columns.
# 编号 | 状态 | 标题 | 作者 | 年/出处 | ID | 引用 | 一句话结论 | PDF
CELL_COUNT = 9


def _clean(text: str) -> str:
    return text.strip().strip("*").strip()


def _split_cells(line: str) -> list[str]:
    """Split a markdown table row into cells, respecting ``[..](..)`` links."""
    # Links can contain | ... but in practice they don't in this file. Split on |.
    parts = line.strip().strip("|").split("|")
    return [p.strip() for p in parts]


def _parse_ids(cell: str) -> tuple[str, str]:
    """Extract arXiv id and DOI from the ID cell."""
    arxiv, doi = "", ""
    for part in re.split(r"·|;", cell):
        part = part.strip()
        m = re.match(r"arXiv[:\s]*(\S+)", part, re.I)
        if m:
            arxiv = m.group(1)
        m = re.match(r"DOI[:\s]*(\S+)", part, re.I)
        if m:
            doi = m.group(1)
    return arxiv, doi


def _parse_year_venue(cell: str) -> tuple[int | None, str]:
    """'2024 / FPGA (ACM)' -> (2024, 'FPGA (ACM)')"""
    m = re.search(r"\b(20\d{2}|19\d{2})\b", cell)
    year = int(m.group(1)) if m else None
    venue = ""
    if "/" in cell:
        venue = cell.split("/", 1)[1].strip()
        venue = re.sub(r"^\d{4}\s*", "", venue).strip()
    return year, venue


def _parse_pdf_path(cell: str) -> str:
    """'[1-FlightLLM.pdf](调研卷宗/KV-cache/1-FlightLLM.pdf)' -> the relative path."""
    m = re.search(r"\]\(([^)]+)\)", cell)
    return m.group(1) if m else ""


def _cell_is_empty(cell: str) -> bool:
    return not cell or cell in ("—", "-", "--", "—")


def _classify_header(cells: list[str]) -> dict[str, int]:
    """Map semantic field names to column positions from a header row."""
    mapping: dict[str, int] = {}
    for i, cell in enumerate(cells):
        c = cell.strip()
        if re.search(r"#|编号", c):
            mapping["num"] = i
        elif "状态" in c:
            mapping["status"] = i
        elif "标题" in c or "名称" in c:
            mapping["title"] = i
        elif "作者" in c or "一作" in c or "机构" in c or "编者" in c:
            mapping["authors"] = i
        elif "年" in c and "出处" in c:
            mapping["year_venue"] = i
        elif "ID" in c.upper() or "链接" in c:
            mapping["ids"] = i
        elif "引用" in c:
            mapping["citations"] = i
        elif "结论" in c or "备注" in c:
            mapping["conclusion"] = i
        elif "PDF" in c.upper() or "本地" in c:
            mapping["pdf"] = i
    return mapping


def parse_index() -> list[dict]:
    """Parse 文献索引.md into a list of entry dicts, header-aware per table."""
    text = INDEX.read_text(encoding="utf-8")
    lines = text.split("\n")
    entries: list[dict] = []
    topic = ""
    colmap: dict[str, int] = {}
    for lineno, line in enumerate(lines, 1):
        if line.startswith("### "):
            topic = line[4:].strip()
            colmap = {}
            continue
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = _split_cells(line)
        if stripped.startswith("|--"):
            continue
        # Header row: contains # or 编号
        if any("#" in c or "编号" in c for c in cells[:2]):
            colmap = _classify_header(cells)
            continue
        # Data row
        if not colmap or "title" not in colmap:
            continue
        def get(key):
            idx = colmap.get(key)
            return _clean(cells[idx]) if idx is not None and idx < len(cells) else ""
        num = get("num")
        if not num or not re.match(r"^[A-Za-z\d]", num):
            continue
        title = get("title")
        if not title:
            continue
        entries.append({
            "topic": topic,
            "num": num,
            "status": get("status"),
            "title": title,
            "authors_raw": get("authors"),
            "year_venue": get("year_venue"),
            "ids_raw": get("ids"),
            "citations": get("citations"),
            "conclusion": get("conclusion"),
            "pdf_cell": get("pdf"),
            "line": lineno,
        })
    return entries


def parse_authors(raw: str) -> list[str]:
    if not raw or raw in ("—", "-"):
        return []
    # "Shulin Zeng 等" -> ["Shulin Zeng"]; "A, B, C" -> [A, B, C]
    for sep in (" 等", " et al", "；", ";"):
        raw = raw.replace(sep, "|")
    parts = [a.strip() for a in re.split(r"\||,", raw) if a.strip()]
    return parts[:12]


def load_abstracts() -> dict[str, dict]:
    """Index papers.json by DOI and arXiv id for abstract supplementation."""
    if not PAPERS_JSON.exists():
        return {}
    data = json.loads(PAPERS_JSON.read_text(encoding="utf-8"))
    by_id: dict[str, dict] = {}
    for item in data:
        for key in ("doi", "arxiv"):
            val = item.get(key, "")
            if val:
                by_id[val.casefold()] = item
    return by_id


def attach_pdfs_from_disk(lib: Library, src: Path,
                          num_to_wid: list[tuple[str, str]]) -> int:
    """Attach PDFs from disk by matching filename to the index's 编号 → work.

    The PDF filenames follow ``<编号>-<短标题>.pdf`` and the index entries store their
    ``编号`` in extras. Longest-prefix match first to disambiguate ``1`` vs ``10``,
    ``NIAC-1`` vs ``NIAC-10``.
    """
    attached = 0
    unmatched: list[str] = []

    # Filter to works that don't have a PDF yet, longest 编号 first.
    candidates = []
    for num, wid in sorted(num_to_wid, key=lambda x: -len(x[0])):
        w = lib.load(wid)
        if w is None or w.has_pdf():
            continue
        candidates.append((num.casefold(), wid))

    pdfs = sorted(src.rglob("*.pdf"))
    print(f"\npdfs on disk: {len(pdfs)}")
    matched_nums: set[str] = set()
    for pdf in pdfs:
        data = pdf.read_bytes()
        if data[:4] != b"%PDF":
            continue
        digest, rel, size = lib.store_file(data, ext="pdf")
        stem = pdf.stem.casefold()
        wid = ""
        for num, w in candidates:
            if num in matched_nums:
                continue
            if stem.startswith(num + "-") or stem == num:
                wid = w
                matched_nums.add(num)
                break
        if wid:
            lib.attach_file(wid, channel="migration", sha256=digest,
                            rel_path=rel, size=size, pdf_url="", license="")
            attached += 1
        else:
            unmatched.append(pdf.name)
    if unmatched:
        print(f"unmatched pdfs ({len(unmatched)}):")
        for u in unmatched[:8]:
            print(f"  {u}")
    return attached


def main() -> int:
    entries = parse_index()
    print(f"parsed {len(entries)} entries from the index")
    abstracts = load_abstracts()
    print(f"abstract supplement: {len(abstracts)} papers indexed")

    lib = Library(Path("papers"))
    lib.ensure()

    created = enriched = skipped = pdfs_attached = 0
    errors: list[str] = []
    num_to_wid: list[tuple[str, str]] = []  # (编号, work_id) for PDF matching

    for entry in entries:
        arxiv, doi = _parse_ids(entry["ids_raw"])
        year, venue = _parse_year_venue(entry["year_venue"])
        authors = parse_authors(entry["authors_raw"])
        title = entry["title"]

        # Supplement the abstract from papers.json
        abstract = ""
        lookup_key = (doi or arxiv).casefold()
        if lookup_key and lookup_key in abstracts:
            abstract = abstracts[lookup_key].get("abstract", "")

        rec = ChannelRecord(
            channel="migration",
            title=title,
            authors=authors,
            year=year,
            venue=venue,
            doi=doi,
            arxiv_id=arxiv,
            abstract=abstract,
        )
        if entry["conclusion"]:
            rec.extras["user_note"] = entry["conclusion"]
        if entry["status"]:
            rec.extras["user_status"] = entry["status"]
        if entry["topic"]:
            rec.extras["topic"] = entry["topic"]
        rec.extras["index_num"] = entry["num"]
        if entry["citations"] and entry["citations"] not in ("—", "-"):
            try:
                rec.extras["citations_at_migration"] = int(entry["citations"])
            except ValueError:
                pass

        try:
            result = lib.upsert_record(rec)
            num_to_wid.append((entry["num"].casefold(), result.work_id))
            if result.action == "created":
                created += 1
            elif result.action == "enriched":
                enriched += 1
            else:
                skipped += 1
        except Exception as exc:
            errors.append(f"L{entry['line']} {title[:50]}: {type(exc).__name__}: {exc}")
            continue

        # Attach the PDF if the index names one and the file exists on disk.
        pdf_rel = _parse_pdf_path(entry["pdf_cell"])
        if pdf_rel:
            pdf_path = SRC / pdf_rel
            if pdf_path.exists():
                data = pdf_path.read_bytes()
                if data[:4] == b"%PDF":
                    digest, rel, size = lib.store_file(data, ext="pdf")
                    lib.attach_file(
                        result.work_id,
                        channel="migration",
                        sha256=digest,
                        rel_path=rel,
                        size=size,
                        pdf_url="",
                        license="",
                    )
                    pdfs_attached += 1

    print(f"\ncreated: {created} | enriched: {enriched} | duplicate: {skipped}")
    print(f"pdfs attached (from index paths): {pdfs_attached}")
    if errors:
        print(f"\nerrors ({len(errors)}):")
        for e in errors[:10]:
            print(f"  {e}")

    # Second pass: scan for PDFs on disk and attach by 编号 match.
    pdfs_attached += attach_pdfs_from_disk(lib, SRC, num_to_wid)

    stats = lib.stats()
    print(f"\nfinal: {stats['works']} works, "
          f"{stats['with_pdf']} with pdf, "
          f"{stats['with_fulltext']} with fulltext, "
          f"{stats['ledger_events']} ledger events")
    lib.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

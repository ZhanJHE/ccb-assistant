import sys
sys.path.insert(0, "src"); sys.path.insert(0, "tools")
from pathlib import Path
from ccb.core.model import ChannelRecord
from ccb.library import Library
from _migrate import parse_index, parse_authors, load_abstracts, _parse_ids, _parse_year_venue

SRC = Path(r"C:\Users\ZhanJH\Desktop\论文学习")
entries = parse_index()
abstracts = load_abstracts()
lib = Library(Path("papers")); lib.ensure()
n = noted = 0
for e in entries:
    arxiv, doi = _parse_ids(e["ids_raw"])
    year, venue = _parse_year_venue(e["year_venue"])
    key = (doi or arxiv).casefold()
    abstract = abstracts.get(key, {}).get("abstract", "") if key else ""
    rec = ChannelRecord(channel="migration", title=e["title"],
                        authors=parse_authors(e["authors_raw"]), year=year, venue=venue,
                        doi=doi, arxiv_id=arxiv, abstract=abstract)
    if e["conclusion"]: rec.extras["user_note"] = e["conclusion"]
    if e["status"]: rec.extras["user_status"] = e["status"]
    if e["topic"]: rec.extras["topic"] = e["topic"]
    rec.extras["index_num"] = e["num"]
    if e["citations"] and e["citations"] not in ("—", "-"):
        try: rec.extras["citations_at_migration"] = int(e["citations"])
        except ValueError: pass
    lib.upsert_record(rec); n += 1
    if rec.extras.get("user_note"): noted += 1
lib.close()
print(f"re-upserted {n} entries, {noted} with notes")

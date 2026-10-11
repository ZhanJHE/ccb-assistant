#!/usr/bin/env python
"""Reproduce the whole topic-generation pipeline on a fixed, offline corpus.

This is the executable record of how the topics module's behaviour was verified: no
network, no third-party dependencies, same corpus every run, and it prints what each
step actually produced rather than asserting a golden string.

    python tools/probe_topics_e2e.py

Exit codes: 0 if every step produced what it should, 1 otherwise.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

# Windows consoles default to GBK, and the prose this probe prints contains em dashes
# and accented venue names. Force UTF-8 on the way out, exactly as the CLI launcher does.
if os.name == "nt":
    os.environ.setdefault("PYTHONUTF8", "1")
    for _stream in ("stdout", "stderr"):
        _handle = getattr(sys, _stream, None)
        if _handle is not None and hasattr(_handle, "reconfigure"):
            try:
                _handle.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from lit.core.model import ChannelRecord  # noqa: E402
from lit.library import Library  # noqa: E402
from lit.topics import candidates as candidates_mod  # noqa: E402
from lit.topics import draft as draft_mod  # noqa: E402
from lit.topics import gaps as gaps_mod  # noqa: E402
from lit.topics import rating as rating_mod  # noqa: E402
from lit.topics import store as store_mod  # noqa: E402
from lit.topics import survey as survey_mod  # noqa: E402

# Two clusters that share "molecular" and almost nothing else: the shape of a
# recombination opening. Titles differ by more than a single character on purpose —
# `title_tokens` drops one-character tokens, so near-identical titles would be
# auto-merged by the library's fuzzy dedup and the probe would measure nothing.
TITLES = [
    "Transformer architectures for molecular property regression",
    "Transformer pretraining on molecular spectra",
    "Transformer decoding of molecular graphs",
    "Transformer distillation for molecular screening",
    "Transformer pruning in molecular pipelines",
    "Transformer interpretability for molecular design",
    "Protein folding with molecular dynamics",
    "Protein docking via molecular simulations",
    "Protein design using molecular sketches",
    "Protein stability from molecular descriptors",
    "Protein ensembles in molecular mechanics",
    "Protein interfaces by molecular contact maps",
]

ABSTRACTS = [
    "We evaluate on the QM9 dataset and compare with SchNet. A key limitation is that "
    "our method does not scale to large systems.",
    "We study molecular systems on the MD17 benchmark. Future work will address transfer "
    "to unseen proteins.",
    "Our approach assumes that molecular structures are static, an idealization we "
    "acknowledge. We compare with DimeNet.",
    "Few works study molecular interpretability. This remains an open problem.",
]

VENUES = ["NeurIPS", "ICML", "CVPR", "Journal of Machine Learning Research"]


def banner(text: str) -> None:
    print()
    print("=" * 72)
    print(text)
    print("=" * 72)


def main() -> int:
    failures: list[str] = []

    with tempfile.TemporaryDirectory() as tmp:
        library = Library(Path(tmp) / "lib")
        library.ensure()
        try:
            banner("0. seed a fixed corpus (12 works, no network)")
            for i, title in enumerate(TITLES):
                library.upsert_record(
                    ChannelRecord(
                        channel="manual",
                        title=title,
                        authors=[f"Author {i}"],
                        year=2020 + i % 4,
                        venue=VENUES[i % len(VENUES)],
                        doi=f"10.1000/probe.{i}",
                        abstract=ABSTRACTS[i % len(ABSTRACTS)],
                    )
                )
            print(f"library holds {library.count()} works")

            banner("1. survey — map the direction")
            # The fixture carries abstracts but no full text, so the full-text
            # threshold is lowered deliberately. With the production defaults (20 works,
            # 5 with full text) this corpus is correctly reported as sufficient: false —
            # which is itself the honest behaviour worth knowing about.
            survey = survey_mod.survey(
                library, "molecular", offline=True, min_works=5, min_fulltext=0
            )
            survey_mod.save_survey(library, survey)
            print(json.dumps({
                "survey_id": survey["survey_id"],
                "found_via": survey["found_via"],
                "corpus": survey["corpus"],
                "sufficient": survey["sufficient"],
                "ccf": survey["ccf"],
                "top_terms": [(t["term"], t["docs"]) for t in survey["terms"][:6]],
            }, indent=2))
            if not survey["sufficient"]:
                failures.append("survey reported insufficient evidence")
            if survey["ccf"]["unmatched"] != 0:
                failures.append("a bundled venue failed to match the CCF catalogue")

            banner("2. gaps — the evidence")
            gap_result = gaps_mod.gaps(library, survey)
            print(json.dumps({
                "usable": gap_result["usable"],
                "gap_kinds": gap_result["gap_kinds"],
                "declared_gaps": len(gap_result["declared_gaps"]),
                "sparse_pairs": [
                    {"terms": p["terms"], "together": p["together"],
                     "expected": p["expected"], "deficit": p["deficit"]}
                    for p in gap_result["sparse_pairs"][:5]
                ],
            }, indent=2))
            for row in gap_result["declared_gaps"][:3]:
                page = f"p.{row['page']}" if row["page"] is not None else "abstract"
                print(f"  [{row['kind']}] [{row['work_id']} {page}] {row['sentence'][:70]}")
            if not gap_result["usable"]:
                failures.append("gap mining found no evidence")
            pairs = {tuple(sorted(p["terms"])) for p in gap_result["sparse_pairs"]}
            if ("protein", "transformer") not in pairs:
                failures.append("the designed sparse pair protein x transformer was not found")

            banner("3. candidates — (evidence x operator), ranked")
            built = candidates_mod.build(library, survey)
            candidates_mod.save_candidates(library, built)
            print(f"generated {built['generated']}, returned {built['returned']}, "
                  f"excluded as already mined {built['excluded_as_mined']}")
            for cand in built["candidates"][:5]:
                print(f"  {cand['candidate_id']}  score {cand['score']:<7} "
                      f"{cand['operator']['id']:<15} {cand['title_hint'][:44]}")
            if not built["candidates"]:
                failures.append("no candidates were generated")
            scores = {c["score"] for c in built["candidates"]}
            if len(scores) < 2:
                failures.append("candidate scores do not vary, so the ranking carries no information")

            banner("4. draft — commit to one, get the skeleton")
            record = draft_mod.draft(library, built["candidates"][0]["candidate_id"])
            print(f"topic_id {record['topic_id']} | sections {len(record['sections'])} "
                  f"| references {len(record['references'])}")
            print(f"context {record['context']}")
            for section in record["sections"]:
                print(f"  {section['n']}. {section['heading']}")
            experiments = next(s for s in record["sections"] if s["n"] == 6)
            print("  observed datasets :", experiments["observed_datasets"][:4])
            print("  observed baselines:", experiments["observed_baselines"][:4])

            # The anchor invariant: no section may carry an unanchored claim.
            for section in record["sections"]:
                for anchor in section["anchors"]:
                    if anchor["kind"] == "quotation":
                        if library.load(anchor["work_id"]) is None:
                            failures.append(f"anchor {anchor['work_id']} is not in the library")
                    elif anchor["kind"] != "statistic":
                        failures.append(f"unknown anchor kind {anchor['kind']!r}")

            banner("5. rate — the CCF estimate, with its reasoning")
            result = rating_mod.rate_and_store(library, record["topic_id"])
            print(f"estimated {result['estimated_ccf']} | upper bound {result['upper_bound']} "
                  f"| confidence {result['confidence']} | steps down {result['steps_down']}")
            for item in result["basis"]:
                print(f"  {item['rule']:<20} {str(item['value']):<10} {item['why'][:56]}")
            for risk in result["risks"]:
                print(f"  risk: {risk[:90]}")
            index = rating_mod.BANDS.index(result["estimated_ccf"])
            if index > rating_mod.BANDS.index(result["upper_bound"]):
                failures.append("the estimate exceeded its own upper bound")

            banner("6. save — commit, export Markdown, retire the key")
            stored = store_mod.load_json(library, "records", record["topic_id"])
            stored["rating"] = result
            stored["status"] = "committed"
            markdown = draft_mod.render_markdown(stored)
            path = store_mod.save_text(library, "drafts", record["topic_id"], markdown)
            store_mod.remember_topic(library, stored)
            print(f"markdown: {path} ({len(markdown)} chars)")
            raw = path.read_bytes()
            if not raw.decode("utf-8"):
                failures.append("draft is not valid UTF-8")
            if "\ufffd" in raw.decode("utf-8"):
                failures.append("draft contains mojibake")

            banner("7. one at a time — the retired key is not proposed again")
            again = candidates_mod.build(library, survey)
            print(f"excluded as already mined: {again['excluded_as_mined']}")
            print(f"mined keys: {len(store_mod.mined_keys(library))}")
            if again["excluded_as_mined"] < 1:
                failures.append("a committed combination was proposed again")

            banner("8. CCF catalogue self-check")
            from lit.topics.ccf import default_catalog

            report = default_catalog().verify()
            print(json.dumps({
                "source": report["source"],
                "venues": report["venues"],
                "by_rank": report["by_rank"],
                "by_kind": report["by_kind"],
                "ok": report["ok"],
                "problems": report["problems"],
            }, indent=2))
            if not report["ok"]:
                failures.append("the bundled CCF catalogue has problems")
        finally:
            library.close()

    banner("RESULT")
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print("all steps produced what they should; no network was used")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""One-off codemod: declare each channel's supported identifier schemes.

Kept in the repository as a record of how the declarations were introduced, but it is
not part of the runtime package.
"""

from __future__ import annotations

import pathlib
import sys

EDITS = {
    "src/lit/channels/arxiv.py": (
        "class ArxivChannel(Channel):\n    spec = ChannelSpec(",
        "class ArxivChannel(Channel):\n"
        "    # arXiv ids, plus titles when that is all the caller has (the search API's\n"
        "    # relevance ranking is loose, so a title lookup is a fallback, not precision).\n"
        '    supports = ("arxiv", "title")\n\n'
        "    spec = ChannelSpec(",
    ),
    "src/lit/channels/crossref.py": (
        "class CrossrefChannel(Channel):\n    spec = ChannelSpec(",
        "class CrossrefChannel(Channel):\n"
        "    # Crossref is a DOI registration agency: a DOI is the only thing it resolves.\n"
        '    supports = ("doi",)\n\n'
        "    spec = ChannelSpec(",
    ),
    "src/lit/channels/openreview.py": (
        "class OpenReviewChannel(Channel):\n    spec = ChannelSpec(",
        "class OpenReviewChannel(Channel):\n"
        '    supports = ("openreview", "title")\n\n'
        "    spec = ChannelSpec(",
    ),
    "src/lit/channels/dblp.py": (
        "class DblpChannel(Channel):\n    spec = ChannelSpec(",
        "class DblpChannel(Channel):\n"
        "    # dblp keys and DOIs; it has no arXiv or OpenReview id lookup endpoint.\n"
        '    supports = ("dblp", "doi", "title")\n\n'
        "    spec = ChannelSpec(",
    ),
    "src/lit/channels/europepmc.py": (
        "class EuropePmcChannel(Channel):\n    spec = ChannelSpec(",
        "class EuropePmcChannel(Channel):\n"
        '    supports = ("doi", "pmid", "title")\n\n'
        "    spec = ChannelSpec(",
    ),
    "src/lit/channels/openalex.py": (
        "class OpenAlexChannel(Channel):\n    spec = ChannelSpec(",
        "class OpenAlexChannel(Channel):\n"
        "    # Broadest resolver: DOI, PMID, its own id, plus a title search fallback for\n"
        "    # records it indexes but that cannot be addressed by a stable identifier.\n"
        '    supports = ("doi", "pmid", "openalex", "title", "arxiv", "openreview",\n'
        '                "acl", "pmlr")\n\n'
        "    spec = ChannelSpec(",
    ),
    "src/lit/channels/paper_search.py": (
        "class PaperSearchChannel(Channel):\n    spec = ChannelSpec(",
        "class PaperSearchChannel(Channel):\n"
        "    # The CLI's only lookup path is a targeted search: fine for identifiers, not\n"
        "    # for a bare title.\n"
        '    supports = ("doi", "arxiv", "pmid", "openreview", "dblp", "acl", "pmlr", "url")\n\n'
        "    spec = ChannelSpec(",
    ),
}


def main() -> int:
    failed = 0
    for path, (old, new) in EDITS.items():
        p = pathlib.Path(path)
        text = p.read_text(encoding="utf-8")
        if old not in text:
            print(f"MISS {path}")
            failed += 1
            continue
        if "supports = (" in text.split(old)[0][-400:]:
            print(f"SKIP {path} (already declared)")
            continue
        p.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")
        print(f"ok   {path}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

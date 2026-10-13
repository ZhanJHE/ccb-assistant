"""Chapter headings in a paper's full text, detected by heuristic.

A passage's *section* is often the strongest retrieval signal after the text itself: a
limitations statement lives in the discussion, a benchmark description in the methods,
and an agent that can filter by section asks better questions. This module finds the
headings; `library.passages` assigns them to chunks, and a chunk inherits the last
heading seen before it — the same way a reader understands where they are.

Pure text computation: no file access, no network. Heuristics only — a heading that is
missed simply leaves the section empty, which is the same behaviour as before this
module existed, so the failure mode is "no gain", never "wrong answer".
"""

from __future__ import annotations

import re

# Section labels seen in academic papers, English and Chinese. Matched at the start of
# a line, case-insensitively.
LABELS: tuple[str, ...] = (
    "abstract", "introduction", "background", "related work", "literature review",
    "methods", "method", "materials", "approach", "results", "evaluation",
    "experiments", "discussion", "limitations", "conclusion", "future work",
    "references", "acknowledg",
    "摘要", "引言", "背景", "相关工作", "文献综述", "方法", "材料", "实验",
    "结果", "讨论", "局限", "结论", "未来工作", "参考文献", "致谢",
)

# "1. Introduction", "2.1 Background", "3 METHODS", "3 结论"
_NUMBERED = re.compile(r"^\s*\d+(?:\.\d+)*\.?\s+(.{1,60}?)\s*:?\s*$")
# A line that is nothing but a label: "Abstract", "Related Work:", "方法"
_BARE = re.compile(
    r"^\s*(" + "|".join(re.escape(label) for label in LABELS) + r")\b[\s:.\-]*$",
    re.IGNORECASE,
)

MAX_HEADING_CHARS = 80


def _heading_label(line: str) -> str:
    """The section name if `line` reads as a heading, else an empty string."""
    if not line or len(line) > MAX_HEADING_CHARS:
        return ""
    numbered = _NUMBERED.match(line)
    if numbered:
        text = numbered.group(1).strip()
        # A number followed by arbitrary prose ("42 participants completed the study")
        # is a sentence, not a heading: require a capital or a CJK character to start.
        if text and (text[0].isupper() or ord(text[0]) > 0x2E7F):
            return text.casefold()
        return ""
    bare = _BARE.match(line)
    if bare:
        return bare.group(1).strip().casefold()
    if line.isupper() and any(label in line.casefold() for label in LABELS):
        return line.casefold()
    return ""


def detect_sections(text: str) -> list[tuple[int, str]]:
    """Headings in `text` as ``(offset, label)``, sorted by offset.

    Offsets are character positions into `text` (the position where the heading line
    starts), so a caller can ask "what is the last heading before this chunk" without
    re-splitting. Lines are separated by ``\\n`` regardless of platform: full text is
    stored with normalised newlines.
    """
    sections: list[tuple[int, str]] = []
    offset = 0
    for line in text.split("\n"):
        label = _heading_label(line.strip())
        if label:
            sections.append((offset, label))
        offset += len(line) + 1
    return sections


__all__ = ["LABELS", "detect_sections"]

"""Source-location value object and helpers.

A :class:`SourceLocation` captures a line/column span plus two pieces of
provenance: ``source`` (which file or JSONL field the code came from) and
``relative_to`` (which coordinate system the numbers are measured against).
Positions are read eagerly from srcML ``--position`` at locate time (single-tree
Option A); after the lxml tree is mutated those attributes go stale, so the
"after" location is derived by diffing the original vs. transformed text instead.

STRICT tree-to-tree rule still holds: we only *read* srcML positions, never use
byte offsets to edit source.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from typing import Any

from lxml import etree

from ..common import POS_NS

# --- relative_to: which coordinate system the line/col are measured against ---
REL_INPUT = "input"     # relative to the extracted snippet/field handed in
REL_FILE = "file"       # relative to a concrete file given as input (a real file location)
REL_OUTPUT = "output"   # relative to the unparsed transformed output
REL_REPO = "repo"       # lifted to a real repository file (recovered, V3)


@dataclass
class SourceLocation:
    """A line/column span with minimal provenance (``source`` + ``relative_to``)."""

    source: str | None = None          # file path or JSONL field name
    relative_to: str = REL_INPUT
    start_line: int | None = None
    start_col: int | None = None
    end_line: int | None = None
    end_col: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "relative_to": self.relative_to,
            "start_line": self.start_line,
            "start_col": self.start_col,
            "end_line": self.end_line,
            "end_col": self.end_col,
        }


def _parse_pos(value: str | None) -> tuple[int | None, int | None]:
    """Parse a srcML ``line:column`` position string into a (line, col) tuple."""
    if not value:
        return None, None
    try:
        line_s, col_s = value.split(":")
        return int(line_s), int(col_s)
    except (ValueError, TypeError):
        return None, None


def from_srcml_node(node: etree._Element) -> SourceLocation | None:
    """Build an input-relative ``SourceLocation`` from ``pos:start`` / ``pos:end``.

    Returns ``None`` when the node carries no position attributes (e.g. the tree
    was parsed without ``--position``). ``source`` is filled in later by
    :func:`apply_input_context`.
    """
    start = node.get(f"{{{POS_NS}}}start")
    end = node.get(f"{{{POS_NS}}}end")
    if not start and not end:
        return None
    sl, sc = _parse_pos(start)
    el, ec = _parse_pos(end)
    return SourceLocation(
        relative_to=REL_INPUT,
        start_line=sl,
        start_col=sc,
        end_line=el,
        end_col=ec,
    )


def apply_input_context(
    loc: SourceLocation,
    input_kind: str,
    source: str | None,
) -> SourceLocation:
    """Annotate an input-relative location with what the input actually was.

    - ``file``: the input is a concrete file, so its coordinates are a real file
      location (``relative_to="file"``).
    - ``function`` / ``snippet`` / ``jsonl_field``: coordinates are only valid
      within the extracted fragment (``relative_to="input"``); lifting to a real
      repository position is deferred to V3.
    """
    loc.source = source
    loc.relative_to = REL_FILE if input_kind == "file" else REL_INPUT
    return loc


def changed_line_spans(
    original: str,
    transformed: str,
    source: str | None = None,
) -> list[SourceLocation]:
    """Return the changed line ranges (in *transformed* coordinates) — Option B.

    Transform-agnostic: line-diffs the two texts and emits one entry per
    contiguous changed hunk, line-level only (columns left ``None``). A pure
    deletion (no extent in the output) is recorded as a zero-width point at the
    output line that now occupies that spot. Returns ``[]`` when nothing changed.
    """
    if original == transformed:
        return []
    a = original.splitlines()
    b = transformed.splitlines()
    n_b = len(b)
    spans: list[SourceLocation] = []
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    for tag, _i1, _i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        if j2 > j1:  # insertion / replacement: real span in the output
            start_line = j1 + 1
            end_line = j2
        else:  # pure deletion: zero-width point in the output
            start_line = end_line = min(j1 + 1, n_b) or 1
        spans.append(
            SourceLocation(
                source=source,
                relative_to=REL_OUTPUT,
                start_line=start_line,
                end_line=end_line,
            )
        )
    return spans

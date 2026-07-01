"""Anchor builder: map a vulnerable line to a node and set ``va:id``.

Given the tree parsed with ``--position`` and a set of target lines (the
vulnerable lines from the dataset's ``line_changes``), the builder finds the
**smallest enclosing statement node** covering each line and attaches a
``va:id`` to it, capturing the original :class:`SourceLocation` as the anchor's
``before`` position.

Coordinate note (important)
---------------------------
In the current single-function pilot the tree being transformed is the extracted
function snippet (``func_vuln``), parsed on its own, so its coordinates are
``input``-relative. SVEN ``line_changes[*].line_no`` is *function-relative*
(line 1 = the function's first line), so it maps **directly** onto the snippet
tree - no repo-coordinate lifting is needed to *find* the node. Lifting the
reported ``before``/``after`` numbers to real repository lines (using V3's
``matched_span`` offset) is a separate, optional reporting concern and is left to
the caller; the builder only records ``input``-relative positions here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from lxml import etree

from ..common import POS_NS, localname
from ..location.model import SourceLocation, apply_input_context, from_srcml_node
from .attr import set_anchor

# Statement-level srcML tags we are willing to anchor onto. Anchoring stays at
# node/statement granularity (matches line/position-level detection);
# sub-expression anchoring is deliberately deferred.
_STMT_TAGS = frozenset({
    "decl_stmt", "expr_stmt", "return", "if_stmt", "if", "else", "elseif",
    "for", "foreach", "while", "do", "switch", "case", "default",
    "break", "continue", "goto", "label", "empty_stmt", "throw",
    "try", "catch", "assert", "using", "typedef",
})

_POS_START = f"{{{POS_NS}}}start"
_POS_END = f"{{{POS_NS}}}end"


@dataclass
class AnchorRequest:
    """A request to anchor a vulnerable line, before any tree lookup."""

    id: str
    line: int                 # 1-based, in the parsed tree's coordinate system
    role: str | None = "sink"


@dataclass
class AnchorSpec:
    """The outcome of injecting one anchor into the tree."""

    id: str
    role: str | None
    injected: bool
    before: SourceLocation | None = None
    node: etree._Element | None = field(default=None, repr=False)
    detail: str | None = None


def _line_span(node: etree._Element) -> tuple[int | None, int | None]:
    """Return the (start_line, end_line) from the node's ``pos:*`` attributes."""
    def _line(value: str | None) -> int | None:
        if not value:
            return None
        head = value.split(":", 1)[0]
        try:
            return int(head)
        except ValueError:
            return None

    return _line(node.get(_POS_START)), _line(node.get(_POS_END))


def find_enclosing_statement(
    unit: etree._Element, line: int
) -> etree._Element | None:
    """Return the smallest statement-level node whose line span covers ``line``.

    "Smallest" = fewest lines spanned; ties are broken by document order (the
    later, i.e. more deeply nested, node wins because ``iter`` yields ancestors
    before descendants and we use a strict ``<`` on span width but prefer a
    deeper node on equal width).
    """
    best: etree._Element | None = None
    best_span: int | None = None
    best_depth = -1
    for el in unit.iter():
        if not isinstance(el.tag, str):
            continue
        if localname(el) not in _STMT_TAGS:
            continue
        sl, el_line = _line_span(el)
        if sl is None or el_line is None:
            continue
        if sl <= line <= el_line:
            span = el_line - sl
            depth = _depth(el, unit)
            if (
                best is None
                or span < best_span
                or (span == best_span and depth > best_depth)
            ):
                best, best_span, best_depth = el, span, depth
    return best


def _depth(node: etree._Element, unit: etree._Element) -> int:
    depth = 0
    cur = node.getparent()
    while cur is not None and cur is not unit.getparent():
        depth += 1
        cur = cur.getparent()
    return depth


def inject_anchors(
    unit: etree._Element,
    requests: list[AnchorRequest],
    input_kind: str = "snippet",
    source: str | None = None,
) -> list[AnchorSpec]:
    """Attach ``va:id`` for each request; return one :class:`AnchorSpec` each.

    Must run **after** ``parse(..., with_position=True)`` and **before** any tree
    mutation, so the eagerly-read ``before`` positions are still valid.
    """
    specs: list[AnchorSpec] = []
    for req in requests:
        node = find_enclosing_statement(unit, req.line)
        if node is None:
            specs.append(
                AnchorSpec(
                    id=req.id, role=req.role, injected=False,
                    detail=f"no statement node covers line {req.line}",
                )
            )
            continue
        set_anchor(node, req.id, req.role)
        before = from_srcml_node(node)
        if before is not None:
            apply_input_context(before, input_kind, source)
        specs.append(
            AnchorSpec(
                id=req.id, role=req.role, injected=True,
                before=before, node=node,
            )
        )
    return specs


# -- dataset glue ----------------------------------------------------------
def target_lines_from_line_changes(
    line_changes: Any, target_field: str | None
) -> list[int]:
    """Best-effort extraction of vulnerable line numbers from ``line_changes``.

    SVEN records carry ``line_changes`` describing the fix diff. For a
    ``func_vuln`` field the vulnerable lines are the ones the fix **deleted**
    (``line_changes.deleted``); for ``func_fixed`` they are the **added** lines.
    Each entry is typically ``{"line_no": N, "line": "..."}`` (function-relative
    ``line_no``); we also tolerate a bare list of ints. Unknown shapes yield an
    empty list rather than raising (the caller then records ``not_attempted``).
    """
    if not line_changes:
        return []

    fixed_fields = {"func_fixed", "fixed_func"}
    key = "added" if (target_field in fixed_fields) else "deleted"

    bucket: Any = None
    if isinstance(line_changes, dict):
        bucket = line_changes.get(key)
        # Some shapes nest under the field name.
        if bucket is None and target_field in line_changes:
            sub = line_changes.get(target_field)
            if isinstance(sub, dict):
                bucket = sub.get(key)
    elif isinstance(line_changes, list):
        bucket = line_changes

    if not bucket:
        return []

    lines: list[int] = []
    for entry in bucket:
        if isinstance(entry, int):
            lines.append(entry)
        elif isinstance(entry, dict):
            n = entry.get("line_no", entry.get("line_number"))
            if isinstance(n, int):
                lines.append(n)
            elif isinstance(n, str) and n.isdigit():
                lines.append(int(n))
    # De-duplicate, keep ascending order for stable VA1, VA2, ... assignment.
    return sorted(set(lines))


def requests_from_lines(lines: list[int], role: str | None = "sink") -> list[AnchorRequest]:
    """Turn ordered target lines into ``VA1``, ``VA2``, ... anchor requests."""
    return [
        AnchorRequest(id=f"VA{i}", line=line, role=role)
        for i, line in enumerate(lines, start=1)
    ]

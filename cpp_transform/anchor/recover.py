"""Post-transform anchor recovery: where did each ``va:id`` node land?

The ``va:id`` attribute is the durable identity, but srcML ``pos:*`` go stale
once the tree is mutated, so the *after* line span is a separate recovery step.

Marker probe (default)
-----------------------
On a **deep copy** of the mutated tree we glue a unique comment token
(``/*__VA_PROBE_VA1__*/``) immediately before each anchored node, unparse the
copy, and read the token's line back from the real srcML output. Because we work
on a throwaway copy, the clean output tree is never touched and no token needs to
be stripped afterwards. The end line is derived from the anchored node's own
reconstructed text (``text_of``), which is verbatim source for a srcML subtree.

Tree-walk fallback
------------------
If the probe token cannot be found (e.g. srcML dropped a comment in some edge
context), we fall back to walking the tree in document order, accumulating the
verbatim text emitted before the node and counting newlines. This needs our
concatenation to match srcML's unparse, which holds because srcML keeps the
original source verbatim inside XML text/tail nodes.
"""

from __future__ import annotations

import copy

from lxml import etree

from ..common import localname, text_of
from ..frontends.base import Frontend, FrontendError
from ..location.model import REL_OUTPUT, SourceLocation
from .attr import find_anchors, get_anchor


def _marker(anchor_id: str) -> str:
    return f"__VA_PROBE_{anchor_id}__"


def _comment_src(anchor_id: str) -> str:
    return f"/*{_marker(anchor_id)}*/"


def recover_anchor_positions(
    unit: etree._Element,
    frontend: Frontend,
    language: str,
    source: str | None = None,
) -> tuple[dict[str, SourceLocation], dict[str, int]]:
    """Recover the after-position of every anchor still present in ``unit``.

    Returns ``(positions, counts)`` where ``positions`` maps ``anchor_id`` to a
    ``REL_OUTPUT`` :class:`SourceLocation` and ``counts`` maps ``anchor_id`` to
    the number of surviving nodes carrying that id (used for classification).
    """
    clean_by_id: dict[str, etree._Element] = {}
    counts: dict[str, int] = {}
    for node in find_anchors(unit):
        aid = get_anchor(node)
        if aid is None:
            continue
        counts[aid] = counts.get(aid, 0) + 1
        clean_by_id.setdefault(aid, node)  # first surviving node per id

    if not clean_by_id:
        return {}, counts

    text = _probe_unparse(unit, frontend, language)

    positions: dict[str, SourceLocation] = {}
    for aid, node in clean_by_id.items():
        start = None
        if text is not None:
            start = _marker_line(text, _marker(aid))
        if start is None:
            start = _walk_start_line(unit, node)
        if start is None:
            continue
        span = text_of(node).count("\n")
        positions[aid] = SourceLocation(
            source=source,
            relative_to=REL_OUTPUT,
            start_line=start,
            end_line=start + span,
        )
    return positions, counts


def _probe_unparse(
    unit: etree._Element, frontend: Frontend, language: str
) -> str | None:
    """Deep-copy, glue markers before each anchor, unparse; return output text."""
    probe = copy.deepcopy(unit)
    for node in find_anchors(probe):
        aid = get_anchor(node)
        if aid is not None:
            _glue_comment_before(node, aid, frontend, language)
    try:
        return frontend.unparse(probe)
    except FrontendError:
        return None


def _glue_comment_before(
    node: etree._Element, anchor_id: str, frontend: Frontend, language: str
) -> None:
    """Insert a comment marker as an immediately-preceding sibling of ``node``.

    ``tail=""`` glues it to the node so the marker lands on the node's start
    line. Falls back to prepending the marker into the node's leading text if a
    comment element cannot be parsed or the node has no parent.
    """
    parent = node.getparent()
    comment_el = _parse_comment(frontend, language, anchor_id)
    if parent is not None and comment_el is not None:
        comment_el.tail = ""
        parent.insert(parent.index(node), comment_el)
        return
    # Last resort: prepend to the node's own text.
    node.text = _comment_src(anchor_id) + (node.text or "")


def _parse_comment(
    frontend: Frontend, language: str, anchor_id: str
) -> etree._Element | None:
    try:
        frag = frontend.parse_fragment(_comment_src(anchor_id) + "\n", language)
    except FrontendError:
        return None
    for el in frag.iter():
        if isinstance(el.tag, str) and localname(el) == "comment":
            return copy.deepcopy(el)
    return None


def _marker_line(text: str, marker: str) -> int | None:
    idx = text.find(marker)
    if idx < 0:
        return None
    return text.count("\n", 0, idx) + 1


def _walk_start_line(
    unit: etree._Element, target: etree._Element
) -> int | None:
    """Count newlines emitted before ``target`` in document order (1-based)."""
    acc: list[str] = []
    if not _emit_until(unit, target, acc):
        return None
    return "".join(acc).count("\n") + 1


def _emit_until(
    el: etree._Element, target: etree._Element, acc: list[str]
) -> bool:
    """Append verbatim text preceding ``target``; stop (True) once reached."""
    if el is target:
        return True
    if el.text:
        acc.append(el.text)
    for child in el:
        if _emit_until(child, target, acc):
            return True
        if child.tail:
            acc.append(child.tail)
    return False

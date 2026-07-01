"""In-tree vulnerability anchoring (V4).

This subsystem gives a vulnerable point a *durable identity* that survives
transformation. After parsing, the :mod:`builder` attaches a custom namespaced
attribute (``va:id="VA1"``) to the smallest enclosing statement node of a
vulnerable line - exactly like srcML's ``pos:*`` attributes, but authored by us
in the lxml layer. The attribute lives only in the XML tree and never appears in
the emitted C/C++ source, so it can neither pollute code nor influence a
downstream detector.

After transforming we XPath the attribute back (:mod:`recover`): found = the
vulnerability node is still there (and we recover its new line span via a
temporary marker probe); not found = ``lost``. :mod:`classify` maps the number
of surviving anchors to a status enum.

The whole subsystem is *additive*: it never rewrites the existing lightweight
``validation`` (V2) or ``repo_validation`` (V3) blocks; it adds a sibling
``vuln_anchor`` block. lxml remains the sole rewriting backend - the srcML binary
is not forked; it only needs to tolerate the extra namespaced attribute on
unparse (the same mechanism already proven by ``pos:*``).

Modules:
  * :mod:`cpp_transform.anchor.attr`     - ``VA_NS`` + set/get/find/copy helpers.
  * :mod:`cpp_transform.anchor.builder`  - line -> smallest enclosing statement
    node -> ``va:id`` injection, capturing the original ``SourceLocation``.
  * :mod:`cpp_transform.anchor.recover`  - post-transform XPath + marker-probe
    position recovery.
  * :mod:`cpp_transform.anchor.classify` - anchor counts -> status enum.
"""

from __future__ import annotations

from .attr import (
    VA_ID,
    VA_NS,
    VA_ROLE,
    clear_anchors,
    copy_anchor,
    find_anchors,
    get_anchor,
    get_role,
    has_anchor,
    set_anchor,
)
from .classify import (
    AMBIGUOUS,
    LOST,
    NOT_ATTEMPTED,
    TRACKED,
    classify,
)

__all__ = [
    "VA_NS",
    "VA_ID",
    "VA_ROLE",
    "set_anchor",
    "get_anchor",
    "get_role",
    "has_anchor",
    "find_anchors",
    "copy_anchor",
    "clear_anchors",
    "classify",
    "TRACKED",
    "LOST",
    "AMBIGUOUS",
    "NOT_ATTEMPTED",
]

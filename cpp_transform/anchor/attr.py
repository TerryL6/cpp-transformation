"""Vulnerability-anchor attribute helpers (mirrors ``POS_NS`` usage).

We store the anchor as a **custom namespaced attribute** on an lxml element,
directly analogous to srcML's ``pos:start`` / ``pos:end``:

* ``va:id``   - the stable anchor identity (e.g. ``"VA1"``).
* ``va:role`` - optional role tag (e.g. ``"sink"``), for reporting only.

Design notes
------------
* The attribute lives only in the XML tree. srcML's ``--unparse`` emits source
  from element text content and ignores unknown namespaced attributes, so these
  never leak into the emitted C/C++ (the same reason ``pos:*`` never leaks).
* Lookups iterate the tree and read the Clark-notation attribute directly rather
  than relying on an XPath prefix. lxml auto-assigns a serialization prefix
  (``ns0:`` etc.) for a namespace not present in the ``<unit>`` nsmap, so keying
  off the namespace URI (not the prefix) keeps ``find_anchors`` robust.
"""

from __future__ import annotations

from lxml import etree

# Our own namespace, deliberately outside srcML's src/cpp/position namespaces so
# it can never collide with anything srcML emits.
VA_NS = "http://cpp-transform/vuln-anchor"

VA = {"va": VA_NS}


def _attr(name: str) -> str:
    """Clark-notation attribute name in the vuln-anchor namespace."""
    return f"{{{VA_NS}}}{name}"


VA_ID = _attr("id")
VA_ROLE = _attr("role")


def set_anchor(node: etree._Element, anchor_id: str, role: str | None = None) -> None:
    """Attach ``va:id`` (and optionally ``va:role``) to ``node``."""
    node.set(VA_ID, anchor_id)
    if role:
        node.set(VA_ROLE, role)


def get_anchor(node: etree._Element) -> str | None:
    """Return the node's ``va:id`` value, or ``None``."""
    return node.get(VA_ID)


def get_role(node: etree._Element) -> str | None:
    """Return the node's ``va:role`` value, or ``None``."""
    return node.get(VA_ROLE)


def has_anchor(node: etree._Element) -> bool:
    return node.get(VA_ID) is not None


def find_anchors(
    unit: etree._Element, anchor_id: str | None = None
) -> list[etree._Element]:
    """Return every element carrying ``va:id`` (optionally filtered by id).

    Iterates in document order. Comments / processing instructions (whose
    ``.tag`` is not a string) are skipped.
    """
    out: list[etree._Element] = []
    for el in unit.iter():
        if not isinstance(el.tag, str):
            continue
        aid = el.get(VA_ID)
        if aid is None:
            continue
        if anchor_id is None or aid == anchor_id:
            out.append(el)
    return out


def copy_anchor(src_node: etree._Element, dst_node: etree._Element) -> bool:
    """Copy all ``va:*`` attributes from ``src_node`` onto ``dst_node``.

    This is the one-liner the anchor-aware propagation contract relies on: a
    transform that removes/replaces an anchored node calls this to carry the
    identity onto the surviving node. A no-op (returns ``False``) when the source
    carries no anchor, so callers can invoke it unconditionally.
    """
    copied = False
    for key, value in src_node.items():
        if key.startswith(f"{{{VA_NS}}}"):
            dst_node.set(key, value)
            copied = True
    return copied


def clear_anchors(unit: etree._Element) -> int:
    """Strip every ``va:*`` attribute from the tree; return how many removed.

    Not needed for normal output (anchors never reach source), but useful in
    tests and if a caller ever wants a pristine tree.
    """
    removed = 0
    for el in unit.iter():
        if not isinstance(el.tag, str):
            continue
        for key in list(el.keys()):
            if key.startswith(f"{{{VA_NS}}}"):
                del el.attrib[key]
                removed += 1
    return removed

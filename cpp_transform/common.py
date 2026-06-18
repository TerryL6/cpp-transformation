"""Shared constants and small helpers for working with srcML XML trees.

STRICT tree-to-tree rule: helpers here only *read* structure or reconstruct the
exact source text of a subtree from its XML text nodes (``itertext``). They
never compute byte offsets into the original source for the purpose of editing.
"""

from __future__ import annotations

from typing import Iterable

from lxml import etree

# srcML namespaces (see srcml output: xmlns / xmlns:cpp).
SRC_NS = "http://www.srcML.org/srcML/src"
CPP_NS = "http://www.srcML.org/srcML/cpp"
POS_NS = "http://www.srcML.org/srcML/position"

NS = {"src": SRC_NS, "cpp": CPP_NS, "pos": POS_NS}


def src(tag: str) -> str:
    """Clark-notation tag in the srcML src namespace."""
    return f"{{{SRC_NS}}}{tag}"


def cpp(tag: str) -> str:
    """Clark-notation tag in the srcML cpp namespace."""
    return f"{{{CPP_NS}}}{tag}"


def localname(el: etree._Element) -> str:
    """Return the local (namespace-stripped) tag name of an element."""
    return etree.QName(el).localname


def text_of(el: etree._Element) -> str:
    """Reconstruct the exact source text covered by ``el`` from its XML text.

    Because srcML keeps the original source verbatim inside XML text/tail nodes,
    joining ``itertext()`` yields the precise source slice for that subtree
    without any byte-offset arithmetic.
    """
    if el is None:
        return ""
    return "".join(el.itertext())


def iter_names(unit: etree._Element) -> Iterable[str]:
    """Yield every identifier-like ``<name>`` leaf text in the tree."""
    for name_el in unit.iter(src("name")):
        if len(name_el) == 0 and name_el.text:
            yield name_el.text


def enclosing_function_name(node: etree._Element) -> str | None:
    """Return the name of the nearest enclosing function definition, if any."""
    cur = node.getparent()
    while cur is not None:
        if localname(cur) in ("function", "constructor", "destructor"):
            name_el = cur.find(src("name"))
            if name_el is not None:
                return text_of(name_el).strip()
            return "<anonymous>"
        cur = cur.getparent()
    return None


def top_level_ancestor(node: etree._Element, unit: etree._Element) -> etree._Element | None:
    """Return the child of ``unit`` that contains ``node`` (its top-level block)."""
    cur = node
    while cur is not None:
        parent = cur.getparent()
        if parent is unit:
            return cur
        cur = parent
    return None

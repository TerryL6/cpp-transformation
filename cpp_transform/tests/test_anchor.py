"""Vulnerability anchoring (V4).

Pure-lxml tests exercise the attribute helpers and dataset glue without srcML;
the srcML-dependent tests (feasibility, builder, propagation, recovery) use the
shared ``frontend`` fixture and are skipped when srcml is unavailable.
"""

from __future__ import annotations

from lxml import etree

from cpp_transform.anchor.attr import (
    VA_NS,
    clear_anchors,
    copy_anchor,
    find_anchors,
    get_anchor,
    get_role,
    has_anchor,
    set_anchor,
)
from cpp_transform.anchor.builder import (
    AnchorRequest,
    find_enclosing_statement,
    inject_anchors,
    requests_from_lines,
    target_lines_from_line_changes,
)
from cpp_transform.anchor.classify import AMBIGUOUS, LOST, TRACKED, classify
from cpp_transform.anchor.finalize import finalize_anchors
from cpp_transform.common import localname
from cpp_transform.pipeline import apply_transform
from cpp_transform.transforms.base import get_transform

DECL_FUNC = "int f(int a){\n    int x = a;\n    return x;\n}\n"


# -- pure lxml: attribute helpers ------------------------------------------
def test_set_get_has_anchor():
    root = etree.Element("unit")
    child = etree.SubElement(root, "decl_stmt")
    assert not has_anchor(child)
    set_anchor(child, "VA1", "sink")
    assert has_anchor(child)
    assert get_anchor(child) == "VA1"
    assert get_role(child) == "sink"


def test_find_and_copy_and_clear_anchor():
    root = etree.Element("unit")
    a = etree.SubElement(root, "decl_stmt")
    b = etree.SubElement(root, "expr_stmt")
    set_anchor(a, "VA1", "sink")

    assert find_anchors(root) == [a]
    assert find_anchors(root, "VA2") == []

    assert copy_anchor(a, b) is True
    assert get_anchor(b) == "VA1"
    assert get_role(b) == "sink"
    # both nodes now carry the anchor
    assert {get_anchor(n) for n in find_anchors(root)} == {"VA1"}
    assert len(find_anchors(root)) == 2

    # copy is a no-op (False) when the source carries nothing
    empty = etree.SubElement(root, "expr_stmt")
    assert copy_anchor(empty, a) is False

    # 2 nodes x {id, role} = 4 va:* attributes
    assert clear_anchors(root) == 4
    assert find_anchors(root) == []


# -- pure: status classification -------------------------------------------
def test_classify_counts():
    assert classify(1) == TRACKED
    assert classify(0) == LOST
    assert classify(2) == AMBIGUOUS


# -- pure: dataset glue ----------------------------------------------------
def test_target_lines_dict_deleted_for_vuln():
    lc = {
        "deleted": [{"line_no": 5, "line": "bad();"}, {"line_no": 3, "line": "x=1;"}],
        "added": [{"line_no": 9, "line": "good();"}],
    }
    assert target_lines_from_line_changes(lc, "func_vuln") == [3, 5]
    assert target_lines_from_line_changes(lc, "func_fixed") == [9]


def test_target_lines_tolerates_bare_ints_and_empty():
    assert target_lines_from_line_changes([2, 2, 1], "func_vuln") == [1, 2]
    assert target_lines_from_line_changes(None, "func_vuln") == []
    assert target_lines_from_line_changes({}, "func_vuln") == []


def test_requests_from_lines_numbering():
    reqs = requests_from_lines([10, 20])
    assert [r.id for r in reqs] == ["VA1", "VA2"]
    assert [r.line for r in reqs] == [10, 20]


# -- srcML: phase-1 feasibility (attribute never leaks into source) --------
def test_unparse_tolerates_and_hides_anchor(frontend):
    unit = frontend.parse(DECL_FUNC, "C", with_position=True)
    node = find_enclosing_statement(unit, 2)
    assert node is not None
    set_anchor(node, "VA1", "sink")

    out = frontend.unparse(unit)
    # The anchor lives only in the XML tree; it must not reach the source text.
    assert "VA1" not in out
    assert "vuln-anchor" not in out
    assert VA_NS not in out
    # ... and the output still reparses cleanly.
    frontend.parse(out, "C")  # raises on failure


# -- srcML: builder picks the smallest enclosing statement -----------------
def test_builder_anchors_the_decl_statement(frontend):
    unit = frontend.parse(DECL_FUNC, "C", with_position=True)
    node = find_enclosing_statement(unit, 2)
    assert node is not None
    assert localname(node) == "decl_stmt"


# -- srcML: end-to-end propagation through variable_chain (tracked) --------
def test_variable_chain_propagates_anchor_tracked(frontend):
    reqs = [AnchorRequest(id="VA1", line=2, role="sink")]
    res = apply_transform(
        frontend, DECL_FUNC, "C", get_transform("variable_chain"),
        pick="first", seed=0, anchors=reqs,
    )
    assert res.status == "success", res.error
    assert res.vuln_anchor is not None
    block = res.vuln_anchor[0]
    assert block["id"] == "VA1"
    assert block["status"] == TRACKED
    assert block["before"] is not None
    assert block["after"] is not None
    # the surviving sink is the chained declaration
    assert "__chain_x" in res.transformed_code


# -- srcML: a removed anchor node is reported lost -------------------------
def test_anchor_lost_when_node_removed(frontend):
    unit = frontend.parse(DECL_FUNC, "C", with_position=True)
    specs = inject_anchors(unit, [AnchorRequest(id="VA1", line=2)], "snippet", None)
    assert specs[0].injected
    node = specs[0].node
    node.getparent().remove(node)

    blocks = finalize_anchors(specs, unit, frontend, "C", None)
    assert blocks[0]["status"] == LOST
    assert blocks[0]["after"] is None

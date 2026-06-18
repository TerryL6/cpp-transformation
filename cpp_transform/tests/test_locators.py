"""Locators are read-only and find the expected candidates."""

from __future__ import annotations

from cpp_transform.locators.call_locator import CallLocator
from cpp_transform.locators.decl_locator import LocalDeclLocator


def test_decl_locator_finds_local_decls(frontend):
    code = "int f(int a){ int x = a; int y = x; return y; }\n"
    unit = frontend.parse(code, "C")
    before = frontend.unparse(unit)
    cands = LocalDeclLocator().find(unit)
    assert len(cands) == 2
    # locator must not mutate the tree
    assert frontend.unparse(unit) == before


def test_decl_locator_works_without_function_wrapper(frontend):
    # No return type -> srcML parses header as <macro> + <block>; we must still
    # find the local declaration.
    code = "myfunc(int a)\n{\n  int x = a;\n  return x;\n}\n"
    unit = frontend.parse(code, "C")
    cands = LocalDeclLocator().find(unit)
    assert any(c.node_type == "decl_stmt" for c in cands)


def test_call_locator_finds_free(frontend):
    code = "#include <stdlib.h>\nvoid g(int *p){ free(p); other(p); }\n"
    unit = frontend.parse(code, "C")
    cands = CallLocator().find(unit)
    callees = {c.metadata["callee"] for c in cands}
    assert "free" in callees
    assert "other" not in callees  # not a memory func

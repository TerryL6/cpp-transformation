"""macro_alias: define + rename + undef, bare-callee only, unique names."""

from __future__ import annotations

from cpp_transform.pipeline import apply_transform
from cpp_transform.transforms.base import get_transform


def _run(frontend, code, language="C", pick="first"):
    return apply_transform(
        frontend, code, language, get_transform("macro_alias"),
        pick=pick, seed=0,
    )


def test_macro_alias_basic(frontend):
    code = "#include <stdlib.h>\nvoid g(int *p){ free(p); }\n"
    res = _run(frontend, code)
    assert res.status == "success", res.error
    out = res.transformed_code
    assert "#define SAFE_FREE free" in out
    assert "#undef SAFE_FREE" in out
    assert "SAFE_FREE(p)" in out
    assert res.validation["structural"]["status"] == "passed"


def test_macro_alias_skips_member_call(frontend):
    # a->free(p) is not a bare-identifier callee.
    code = "void g(struct A *a, int *p){ a->free(p); }\n"
    res = _run(frontend, code)
    assert res.status == "skipped"
    assert res.transformed_code == code


def test_macro_alias_unique_names_for_multiple(frontend):
    code = (
        "#include <stdlib.h>\n"
        "void g(int *a, int *b){ free(a); free(b); }\n"
    )
    res = _run(frontend, code, pick="all")
    out = res.transformed_code
    assert "#define SAFE_FREE free" in out
    assert "#define SAFE_FREE_1 free" in out
    assert out.count("#undef") == 2

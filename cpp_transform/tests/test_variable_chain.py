"""variable_chain: applies to simple types, skips risky ones, avoids clashes."""

from __future__ import annotations

import pytest

from cpp_transform.pipeline import apply_transform
from cpp_transform.transforms.base import get_transform


def _run(frontend, code, language="C", pick="first"):
    return apply_transform(
        frontend, code, language, get_transform("variable_chain"),
        pick=pick, seed=0,
    )


ACCEPT = [
    ("C", "int f(int a){ int x = a; return x; }\n"),
    ("C", "int f(int *q){ int *p = q; return *p; }\n"),
    ("C", "long f(long a){ unsigned long x = a; return x; }\n"),
    ("C", "char* f(char* q){ char* p = q; return p; }\n"),
]

SKIP = [
    ("C", "int f(){ int a = 1, b = 2; return a + b; }\n", "multiple declarators"),
    ("C", "int f(){ int a[3] = {1, 2, 3}; return a[0]; }\n", "array/aggregate"),
    ("C", "int f(int a){ volatile int x = a; return x; }\n", "volatile"),
    ("C", "int f(){ static int x = 0; return x; }\n", "static storage"),
    ("C++", "int f(int a){ int& r = a; return r; }\n", "reference"),
    ("C", "struct S{int v;}; int f(struct S s){ struct S t = s; return t.v; }\n",
     "struct value"),
]


@pytest.mark.parametrize("language,code", ACCEPT)
def test_variable_chain_accepts_simple(frontend, language, code):
    res = _run(frontend, code, language)
    assert res.status == "success", res.error
    assert res.changed
    assert "__chain_" in res.transformed_code
    assert res.validation["srcml_reparse"]["status"] == "passed"
    assert res.validation["structural"]["status"] == "passed"


@pytest.mark.parametrize("language,code,why", SKIP)
def test_variable_chain_skips_risky(frontend, language, code, why):
    res = _run(frontend, code, language)
    assert res.status == "skipped", f"{why}: {res.status} {res.error}"
    assert res.transformed_code == code  # untouched


def test_variable_chain_avoids_name_collision(frontend):
    # __chain_x already exists (as a parameter); the generated name must differ.
    code = "int f(int __chain_x){ int x = __chain_x; return x; }\n"
    res = _run(frontend, code)
    assert res.status == "success", res.error
    assert "__chain_x_1" in res.transformed_code


def test_variable_chain_value_preserved_structurally(frontend):
    code = "int f(int a){ int x = a; return x; }\n"
    res = _run(frontend, code)
    # x is still ultimately assigned from a (via the chain temp)
    assert "= a;" in res.transformed_code
    assert "= __chain_x;" in res.transformed_code

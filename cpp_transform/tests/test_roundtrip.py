"""Round-trip: parse -> unparse must be exact and reparse cleanly."""

from __future__ import annotations

import pytest

from cpp_transform.validation.validators import roundtrip_metrics

SNIPPETS = [
    ("C", "int f(int a){ int x = a; return x; }\n"),
    ("C", "#include <stdlib.h>\nvoid g(int *p){ free(p); }\n"),
    ("C", "int h(){ /* keep comment */ int y = 0; return y; }\n"),
    ("C++", "int f(int a){ int x = a; return x; }\n"),
    ("C", "#if X\nint a = 1;\n#endif\n"),
]


@pytest.mark.parametrize("language,code", SNIPPETS)
def test_roundtrip_exact(frontend, language, code):
    m = roundtrip_metrics(frontend, code, language)
    assert m["reparse_ok"], m
    assert m["exact_equal"], m
    assert m["normalized_equal"], m

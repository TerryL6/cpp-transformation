"""Pick strategies select the expected subsets."""

from __future__ import annotations

from cpp_transform.model.candidate import Candidate
from cpp_transform.pick.strategies import get_strategy


def _cands(n, fn="f"):
    return [
        Candidate(cid=f"c{i}", node_type="decl_stmt", node=None,
                  enclosing_function=fn)
        for i in range(n)
    ]


def test_first():
    cs = _cands(3)
    assert get_strategy("first")(cs, None) == cs[:1]


def test_all():
    cs = _cands(3)
    assert get_strategy("all")(cs, None) == cs


def test_random_is_reproducible():
    cs = _cands(5)
    a = get_strategy("random")(cs, 123)
    b = get_strategy("random")(cs, 123)
    assert a == b
    assert len(a) == 1


def test_one_per_function():
    cs = (
        _cands(2, "f")
        + _cands(2, "g")
    )
    out = get_strategy("one_per_function")(cs, None)
    fns = {c.enclosing_function for c in out}
    assert fns == {"f", "g"}
    assert len(out) == 2

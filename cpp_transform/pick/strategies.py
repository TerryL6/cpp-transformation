"""Pick strategies.

A strategy takes the full candidate list and returns the subset to transform.
v1 ships: first, random (reproducible via seed), all, one_per_function. More
(e.g. highest-confidence, transform-specific rules) can be added later.
"""

from __future__ import annotations

import random
from typing import Callable

from ..model.candidate import Candidate

PickFn = Callable[[list[Candidate], int | None], list[Candidate]]


def pick_first(cands: list[Candidate], seed: int | None = None) -> list[Candidate]:
    return cands[:1]


def pick_all(cands: list[Candidate], seed: int | None = None) -> list[Candidate]:
    return list(cands)


def pick_random(cands: list[Candidate], seed: int | None = None) -> list[Candidate]:
    if not cands:
        return []
    rng = random.Random(seed)
    return [rng.choice(cands)]


def pick_one_per_function(
    cands: list[Candidate], seed: int | None = None
) -> list[Candidate]:
    rng = random.Random(seed)
    by_fn: dict[str | None, list[Candidate]] = {}
    for c in cands:
        by_fn.setdefault(c.enclosing_function, []).append(c)
    out: list[Candidate] = []
    for fn in sorted(by_fn, key=lambda x: (x is None, x or "")):
        group = by_fn[fn]
        out.append(group[0] if seed is None else rng.choice(group))
    return out


STRATEGIES: dict[str, PickFn] = {
    "first": pick_first,
    "all": pick_all,
    "random": pick_random,
    "one_per_function": pick_one_per_function,
}


def get_strategy(name: str) -> PickFn:
    if name not in STRATEGIES:
        raise KeyError(
            f"unknown pick strategy {name!r}; choose from {sorted(STRATEGIES)}"
        )
    return STRATEGIES[name]

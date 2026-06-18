"""Transformation interface + registry.

Adding a new transformation = subclass ``Transformation``, implement the four
methods, and decorate with ``@register``. Nothing else needs to change.

STRICT tree-to-tree contract for ``apply``: it must mutate ``ctx.unit`` (the
lxml/srcML tree) only. New nodes are built by parsing small snippets via
``ctx.frontend.parse_fragment`` and grafting the resulting subtrees. No byte
offsets, no source-string splicing.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..model.candidate import Candidate
from ..model.context import TransformContext


class Transformation(ABC):
    #: unique transform name (CLI/report key)
    name: str = ""
    #: family grouping (e.g. "dataflow", "preprocessor")
    family: str = ""

    @abstractmethod
    def find_candidates(self, ctx: TransformContext) -> list[Candidate]:
        ...

    @abstractmethod
    def can_apply(self, cand: Candidate, ctx: TransformContext) -> bool:
        ...

    @abstractmethod
    def apply(self, cand: Candidate, ctx: TransformContext) -> None:
        """Mutate ``ctx.unit`` in place to realize the transform on ``cand``."""

    @abstractmethod
    def structural_check(self, cand: Candidate, ctx: TransformContext) -> bool:
        """Transform-specific assertion that the edit landed as intended."""


REGISTRY: dict[str, Transformation] = {}


def register(cls: type[Transformation]) -> type[Transformation]:
    inst = cls()
    if not inst.name:
        raise ValueError(f"{cls.__name__} must define a non-empty name")
    if inst.name in REGISTRY:
        raise ValueError(f"duplicate transform name: {inst.name}")
    REGISTRY[inst.name] = inst
    return cls


def get_transform(name: str) -> Transformation:
    if name not in REGISTRY:
        raise KeyError(
            f"unknown transform {name!r}; available: {sorted(REGISTRY)}"
        )
    return REGISTRY[name]

"""Transformation interface + registry.

Adding a new transformation = subclass ``Transformation``, implement the four
methods, and decorate with ``@register``. Nothing else needs to change.

STRICT tree-to-tree contract for ``apply``: it must mutate ``ctx.unit`` (the
lxml/srcML tree) only. New nodes are built by parsing small snippets via
``ctx.frontend.parse_fragment`` and grafting the resulting subtrees. No byte
offsets, no source-string splicing.

ANCHOR-AWARE PROPAGATION CONTRACT (V4): a transform that **removes, replaces, or
regenerates** a node must carry any vulnerability-anchor attributes (``va:*``)
onto the surviving/result node so the anchor is not lost. A plain *move* needs
nothing (the attribute lives on the element and travels with it). For
remove/replace/regenerate, call :func:`carry_anchor` from the old node onto the
node that should inherit the identity **before** discarding the old one. When a
transform legitimately splits one node into several, pin the anchor onto the
single primary sink (the piece that still carries the vulnerable value), not
every fragment. :func:`carry_anchor` is a no-op when no anchor is present, so it
is safe to call unconditionally and costs nothing when anchoring is off.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from lxml import etree

from ..model.candidate import Candidate
from ..model.context import TransformContext


def carry_anchor(src_node: etree._Element, *dst_nodes: etree._Element) -> None:
    """Propagate ``va:*`` anchor attributes from ``src_node`` onto each dst.

    The one call that satisfies the anchor-aware propagation contract above.
    Imported lazily so the anchor subsystem stays optional and the core
    transform interface carries no hard dependency on it.
    """
    from ..anchor.attr import copy_anchor

    for dst in dst_nodes:
        copy_anchor(src_node, dst)


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

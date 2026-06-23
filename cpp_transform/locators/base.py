"""Locator protocol and shared helpers.

Locators are strictly read-only: they walk the srcML tree and return structured
``Candidate`` objects. They must not mutate the tree.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from lxml import etree

from ..common import enclosing_function_name, src, text_of
from ..location.model import SourceLocation, from_srcml_node
from ..model.candidate import Candidate


def source_location(node: etree._Element) -> SourceLocation | None:
    """Eagerly freeze a node's srcML position into a ``SourceLocation``.

    Returns ``None`` if the tree was parsed without ``--position``. Coordinates
    are captured now (input-relative) so later tree mutation cannot make them
    stale; the pipeline enriches basis/mapping/tab metadata afterwards.
    """
    return from_srcml_node(node)


class Locator(ABC):
    #: short identifier used in candidate ids
    kind: str = "candidate"

    @abstractmethod
    def find(self, unit: etree._Element) -> list[Candidate]:
        ...

    def _make_candidate(
        self,
        node: etree._Element,
        index: int,
        node_type: str,
        applicable: list[str],
        **metadata,
    ) -> Candidate:
        return Candidate(
            cid=f"{self.kind}:{index}",
            node_type=node_type,
            node=node,
            enclosing_function=enclosing_function_name(node),
            original_text=text_of(node).strip(),
            applicable_transforms=applicable,
            source_location=source_location(node),
            metadata=metadata,
        )

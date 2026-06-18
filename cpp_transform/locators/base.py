"""Locator protocol and shared helpers.

Locators are strictly read-only: they walk the srcML tree and return structured
``Candidate`` objects. They must not mutate the tree.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from lxml import etree

from ..common import NS, enclosing_function_name, src, text_of
from ..model.candidate import Candidate


def source_location(node: etree._Element) -> dict[str, int] | None:
    """Best-effort (line, col) from srcML position attributes if present."""
    start = node.get(f"{{{NS['pos']}}}start")
    if not start:
        return None
    try:
        line, col = start.split(":")
        return {"line": int(line), "col": int(col)}
    except (ValueError, TypeError):
        return None


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

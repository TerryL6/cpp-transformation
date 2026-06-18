"""Candidate model.

A Candidate is a *structured description* of a transformable location. Locators
return Candidates; they never modify the tree. The live lxml node is kept on the
object (``node``) for the transform stage but excluded from serialization.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from lxml import etree


@dataclass
class Candidate:
    cid: str
    node_type: str
    node: etree._Element = field(repr=False)
    enclosing_function: str | None = None
    original_text: str = ""
    applicable_transforms: list[str] = field(default_factory=list)
    source_location: dict[str, int] | None = None
    type_info: dict[str, Any] | None = None
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serializable view (drops the live lxml node)."""
        return {
            "cid": self.cid,
            "node_type": self.node_type,
            "enclosing_function": self.enclosing_function,
            "original_text": self.original_text,
            "applicable_transforms": self.applicable_transforms,
            "source_location": self.source_location,
            "type_info": self.type_info,
            "confidence": self.confidence,
            "metadata": self.metadata,
        }

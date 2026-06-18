"""Frontend protocol.

A Frontend turns C/C++ source into a mutable structured tree and back. The
contract is deliberately small so alternative backends could be added later, but
v1 only ships the srcML implementation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from lxml import etree


class FrontendError(RuntimeError):
    """Raised when the underlying parser/unparser fails."""


class Frontend(ABC):
    @abstractmethod
    def parse(self, code: str, language: str) -> etree._Element:
        """Parse ``code`` and return the root ``<unit>`` element (mutable)."""

    @abstractmethod
    def unparse(self, unit: etree._Element) -> str:
        """Serialize a structured tree back into source code."""

    def parse_fragment(self, code: str, language: str) -> etree._Element:
        """Parse a small snippet, returning its ``<unit>``.

        Used by transformations to build new subtrees that are then grafted into
        the main tree (strict tree-to-tree construction, never string splicing
        into the output source).
        """
        return self.parse(code, language)

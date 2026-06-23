"""TransformContext: shared state passed through the pipeline.

Holds the live srcML tree, the language, the frontend (so transforms can parse
small snippets to build subtrees), and a name generator that guarantees freshly
introduced identifiers do not collide with anything already in the tree.
"""

from __future__ import annotations

from lxml import etree

from ..common import iter_names
from ..frontends.base import Frontend


class NameGenerator:
    """Generates identifiers that are unique across the whole tree."""

    def __init__(self, used: set[str]) -> None:
        self._used = set(used)

    def fresh(self, base: str) -> str:
        if base not in self._used:
            self._used.add(base)
            return base
        i = 1
        while f"{base}_{i}" in self._used:
            i += 1
        name = f"{base}_{i}"
        self._used.add(name)
        return name

    def reserve(self, name: str) -> None:
        self._used.add(name)

    def __contains__(self, name: str) -> bool:
        return name in self._used


class TransformContext:
    def __init__(
        self,
        unit: etree._Element,
        language: str,
        frontend: Frontend,
        input_kind: str = "snippet",
        source: str | None = None,
    ) -> None:
        self.unit = unit
        self.language = language
        self.frontend = frontend
        # What the input represents, for source-location semantics:
        # "file" | "function" | "snippet" | "jsonl_field".
        self.input_kind = input_kind
        # File path (for "file") or JSONL field name (for "jsonl_field").
        self.source = source
        self.names = NameGenerator(set(iter_names(unit)))

    def refresh_names(self) -> None:
        """Re-scan identifiers (call after structural edits add new names)."""
        for n in iter_names(self.unit):
            self.names.reserve(n)

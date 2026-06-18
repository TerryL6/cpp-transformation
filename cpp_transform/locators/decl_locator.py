"""Locate local variable declarations with an initializer.

Returns every ``decl_stmt`` that lives inside a function body. Type/safety
filtering is intentionally left to the transformation's ``can_apply`` so the
locator stays a generic, reusable discovery layer.
"""

from __future__ import annotations

from lxml import etree

from ..common import NS, src
from ..model.candidate import Candidate
from .base import Locator


class LocalDeclLocator(Locator):
    kind = "decl"

    def find(self, unit: etree._Element) -> list[Candidate]:
        candidates: list[Candidate] = []
        # decl_stmt nodes inside any block body. We deliberately do NOT require a
        # <function> ancestor: SVEN/PrimeVul snippets are often extracted without
        # their return type, so srcML parses the header as <macro> followed by a
        # top-level <block>. Anchoring on block_content keeps us at local scope
        # (block_content only exists inside function bodies / compound stmts)
        # while still covering those headerless snippets.
        decls = unit.xpath(
            ".//src:block/src:block_content/src:decl_stmt",
            namespaces=NS,
        )
        for i, decl_stmt in enumerate(decls):
            decl_children = decl_stmt.findall(src("decl"))
            has_init = any(d.find(src("init")) is not None for d in decl_children)
            type_info = {
                "num_declarators": len(decl_children),
                "has_init": has_init,
            }
            cand = self._make_candidate(
                decl_stmt,
                i,
                node_type="decl_stmt",
                applicable=["variable_chain"],
            )
            cand.type_info = type_info
            candidates.append(cand)
        return candidates

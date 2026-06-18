"""Locate function-call sites, with a focus on memory-management calls.

Returns ``call`` nodes whose callee is a bare identifier. The transform layer
decides which callee names it cares about and which forms are safe.
"""

from __future__ import annotations

from lxml import etree

from ..common import NS, src, text_of
from ..model.candidate import Candidate
from .base import Locator

#: default memory-management callees of interest
MEMORY_FUNCS = {"free", "malloc", "calloc", "realloc", "reallocf"}


class CallLocator(Locator):
    kind = "call"

    def __init__(self, names: set[str] | None = None) -> None:
        self.names = names if names is not None else set(MEMORY_FUNCS)

    def find(self, unit: etree._Element) -> list[Candidate]:
        candidates: list[Candidate] = []
        calls = unit.xpath(".//src:call", namespaces=NS)
        idx = 0
        for call in calls:
            name_el = call.find(src("name"))
            if name_el is None:
                continue
            # bare-identifier callee: no nested name/operator children.
            is_bare = len(name_el) == 0 and bool(name_el.text)
            callee = (name_el.text or "").strip() if is_bare else text_of(name_el).strip()
            if self.names and callee not in self.names:
                continue
            cand = self._make_candidate(
                call,
                idx,
                node_type="call",
                applicable=["macro_alias"],
                callee=callee,
                bare_callee=is_bare,
            )
            cand.type_info = {"callee": callee, "bare_callee": is_bare}
            candidates.append(cand)
            idx += 1
        return candidates

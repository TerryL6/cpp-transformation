"""macro_alias: a preprocessor / tree round-trip demonstration transform.

For a bare-identifier memory call such as ``free(p)`` it:
  1. grafts a ``#define <UNIQUE_ALIAS> free`` directive subtree before the
     enclosing top-level definition,
  2. rewrites the matched call's callee name to ``<UNIQUE_ALIAS>``,
  3. grafts a matching ``#undef <UNIQUE_ALIAS>`` after that definition so the
     macro cannot leak into later code.

It is NOT a general data-flow transform; it exercises the preprocessor markup
and the graft/unparse round trip. The next general data-flow transform planned
is ``array_indirection``.

Constraints: unique macro name (collision-checked across the whole tree),
bare-identifier callee only (skips ``a->free()``, ``(*fp)()``, member/qualified
calls), type-agnostic, valid for both C and C++.
"""

from __future__ import annotations

import copy

from lxml import etree

from ..common import NS, cpp, src, text_of, top_level_ancestor
from ..locators.call_locator import MEMORY_FUNCS, CallLocator
from ..model.candidate import Candidate
from ..model.context import TransformContext
from .base import Transformation, register


def _bare_callee(call: etree._Element) -> str | None:
    name_el = call.find(src("name"))
    if name_el is None:
        return None
    if len(name_el) > 0 or not (name_el.text or "").strip():
        return None  # compound callee (member/qualified/function-pointer)
    return name_el.text.strip()


@register
class MacroAlias(Transformation):
    name = "macro_alias"
    family = "preprocessor"

    def __init__(self) -> None:
        self.targets = set(MEMORY_FUNCS)

    def find_candidates(self, ctx: TransformContext) -> list[Candidate]:
        out: list[Candidate] = []
        for cand in CallLocator(self.targets).find(ctx.unit):
            if self.can_apply(cand, ctx):
                cand.applicable_transforms = [self.name]
                out.append(cand)
        return out

    def can_apply(self, cand: Candidate, ctx: TransformContext) -> bool:
        callee = _bare_callee(cand.node)
        return callee is not None and callee in self.targets

    def apply(self, cand: Candidate, ctx: TransformContext) -> None:
        call = cand.node
        callee = _bare_callee(call)
        if callee is None:
            raise ValueError("candidate no longer applicable")

        alias = ctx.names.fresh(f"SAFE_{callee.upper()}")

        define_frag = ctx.frontend.parse_fragment(
            f"#define {alias} {callee}\n", ctx.language
        )
        undef_frag = ctx.frontend.parse_fragment(
            f"#undef {alias}\n", ctx.language
        )
        define_el = define_frag.find(cpp("define"))
        undef_el = undef_frag.find(cpp("undef"))
        if define_el is None or undef_el is None:
            raise ValueError("srcML did not produce cpp:define/cpp:undef subtree")

        anchor = top_level_ancestor(call, ctx.unit)
        if anchor is None:
            raise ValueError("could not locate a top-level anchor for the call")
        parent = anchor.getparent()
        idx = parent.index(anchor)

        d = copy.deepcopy(define_el)
        u = copy.deepcopy(undef_el)
        d.tail = "\n"
        # place #undef right after the anchor, inheriting its trailing space
        u.tail = anchor.tail if anchor.tail is not None else "\n"
        anchor.tail = "\n"

        parent.insert(idx, d)
        parent.insert(parent.index(anchor) + 1, u)

        # rewrite callee name (text node) on the matched call
        name_el = call.find(src("name"))
        name_el.text = alias

        cand.metadata["alias"] = alias
        cand.metadata["callee"] = callee
        ctx.names.reserve(alias)

    def structural_check(self, cand: Candidate, ctx: TransformContext) -> bool:
        alias = cand.metadata.get("alias")
        if not alias:
            return False
        defines = ctx.unit.xpath(".//cpp:define", namespaces=NS)
        undefs = ctx.unit.xpath(".//cpp:undef", namespaces=NS)
        has_define = any(alias in text_of(d) for d in defines)
        has_undef = any(alias in text_of(u) for u in undefs)
        name_el = cand.node.find(src("name"))
        renamed = name_el is not None and (name_el.text or "").strip() == alias
        return has_define and has_undef and renamed

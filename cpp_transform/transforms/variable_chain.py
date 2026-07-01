"""variable_chain: introduce one extra copy hop for a local declaration.

    T x = E;            -->     T __chain_x = E;
                                T x = __chain_x;

This is a general, data-flow-relevant transformation: it adds a benign extra
assignment hop while preserving the value reaching ``x``. The reused type ``T``
is read directly from the existing declaration subtree (no type inference).

Safety gating (per plan): only applied to clearly-simple types --
primitives, enums, and plain pointers (``T*``). It skips class/struct objects,
template types, references, arrays, aggregate/brace initializers, ``volatile``,
storage-class (static/extern/thread_local), and multiple declarators, because an
extra temporary there could change C++ copy/move/destructor/lifetime semantics.

Construction is strict tree-to-tree: a small snippet is parsed by the frontend
and the resulting ``decl_stmt`` subtrees are grafted in place of the original.
"""

from __future__ import annotations

import copy

from lxml import etree

from ..common import NS, localname, src, text_of
from ..model.candidate import Candidate
from ..model.context import TransformContext
from .base import Transformation, carry_anchor, register

_PRIMITIVE = {
    "int", "char", "short", "long", "float", "double", "void",
    "signed", "unsigned", "bool", "_Bool", "wchar_t", "char16_t", "char32_t",
}
_BENIGN_QUALIFIERS = {
    "const", "register", "auto", "restrict", "__restrict", "__restrict__",
    "constexpr",
}
_REJECT_QUALIFIERS = {
    "volatile", "static", "extern", "thread_local", "_Thread_local", "mutable",
}


def _single_decl(decl_stmt: etree._Element) -> etree._Element | None:
    decls = decl_stmt.findall(src("decl"))
    return decls[0] if len(decls) == 1 else None


def _declared_name_el(decl: etree._Element) -> etree._Element | None:
    """The declarator's <name> (after <type>, before <init>)."""
    for child in decl:
        ln = localname(child)
        if ln == "type":
            continue
        if ln == "name":
            return child
        if ln == "init":
            break
    return None


def _analyze(decl_stmt: etree._Element) -> dict | None:
    decl = _single_decl(decl_stmt)
    if decl is None:
        return None  # multiple declarators or none

    type_el = decl.find(src("type"))
    if type_el is None:
        return None

    name_el = _declared_name_el(decl)
    # Only a *simple* identifier declarator. A compound <name> (children) means
    # array, function pointer, qualified name, etc. -> reject.
    if name_el is None or len(name_el) > 0 or not (name_el.text or "").strip():
        return None
    var_name = name_el.text.strip()
    if not var_name.isidentifier():
        return None

    init_el = decl.find(src("init"))
    if init_el is None:
        return None
    init_text = text_of(init_el).lstrip()
    if not init_text.startswith("="):
        return None  # constructor-init T x(...) or other forms
    if "{" in text_of(init_el):
        return None  # aggregate / brace initialization
    expr_el = init_el.find(src("expr"))
    if expr_el is None:
        return None

    modifiers = [(m.text or "") for m in type_el.findall(src("modifier"))]
    has_ref = any("&" in m for m in modifiers)
    has_ptr = any("*" in m for m in modifiers)
    has_template = type_el.find(".//" + src("argument_list")) is not None
    if has_ref or has_template:
        return None

    type_text = " ".join(text_of(type_el).split())
    tokens = type_text.replace("*", " ").replace("&", " ").split()
    if any(t in _REJECT_QUALIFIERS for t in tokens):
        return None

    content = [t for t in tokens if t not in _BENIGN_QUALIFIERS]
    if has_ptr:
        kind = "pointer"  # copying a pointer value is safe regardless of pointee
    elif "enum" in content:
        kind = "enum"
    elif content and all(t in _PRIMITIVE for t in content):
        kind = "primitive"
    else:
        return None  # struct/class/union/unknown typedef -> reject

    return {
        "decl": decl,
        "type_text": type_text,
        "var_name": var_name,
        "expr_text": text_of(expr_el).strip(),
        "kind": kind,
    }


@register
class VariableChain(Transformation):
    name = "variable_chain"
    family = "dataflow"

    def find_candidates(self, ctx: TransformContext) -> list[Candidate]:
        from ..locators.decl_locator import LocalDeclLocator

        out: list[Candidate] = []
        for cand in LocalDeclLocator().find(ctx.unit):
            info = _analyze(cand.node)
            if info is None:
                continue
            cand.applicable_transforms = [self.name]
            cand.type_info = {"type": info["type_text"], "kind": info["kind"]}
            out.append(cand)
        return out

    def can_apply(self, cand: Candidate, ctx: TransformContext) -> bool:
        return _analyze(cand.node) is not None

    def apply(self, cand: Candidate, ctx: TransformContext) -> None:
        info = _analyze(cand.node)
        if info is None:
            raise ValueError("candidate no longer applicable")

        var_name = info["var_name"]
        type_text = info["type_text"]
        expr_text = info["expr_text"]
        chain_name = ctx.names.fresh(f"__chain_{var_name}")

        snippet = (
            f"{type_text} {chain_name} = {expr_text}; "
            f"{type_text} {var_name} = {chain_name};\n"
        )
        frag = ctx.frontend.parse_fragment(snippet, ctx.language)
        new_decls = frag.findall(src("decl_stmt"))
        if len(new_decls) != 2:
            raise ValueError(
                f"expected 2 decl_stmt from snippet, got {len(new_decls)}"
            )

        decl_stmt = cand.node
        parent = decl_stmt.getparent()
        idx = parent.index(decl_stmt)
        orig_tail = decl_stmt.tail

        n0 = copy.deepcopy(new_decls[0])
        n1 = copy.deepcopy(new_decls[1])
        n0.tail = " "
        n1.tail = orig_tail

        # Anchor-aware propagation (V4): the original decl_stmt is removed and
        # replaced by two new statements. Carry any vulnerability anchor onto the
        # primary sink -- ``n1`` (``T x = __chain_x;``), which still declares the
        # original variable and holds the value that reaches downstream uses.
        # No-op when the node carries no anchor.
        carry_anchor(decl_stmt, n1)

        parent.insert(idx, n0)
        parent.insert(idx + 1, n1)
        parent.remove(decl_stmt)

        cand.metadata["chain_name"] = chain_name
        cand.metadata["var_name"] = var_name
        ctx.refresh_names()

    def structural_check(self, cand: Candidate, ctx: TransformContext) -> bool:
        chain_name = cand.metadata.get("chain_name")
        var_name = cand.metadata.get("var_name")
        if not chain_name or not var_name:
            return False
        found_chain = False
        found_link = False
        for decl in ctx.unit.xpath(".//src:decl", namespaces=NS):
            name_el = _declared_name_el(decl)
            if name_el is None or len(name_el) > 0:
                continue
            declared = (name_el.text or "").strip()
            if declared == chain_name:
                found_chain = True
            if declared == var_name:
                init_el = decl.find(src("init"))
                if init_el is not None and chain_name in text_of(init_el):
                    found_link = True
        return found_chain and found_link

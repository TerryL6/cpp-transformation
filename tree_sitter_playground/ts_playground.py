from __future__ import annotations

import argparse
from pathlib import Path

from tree_sitter import Language, Node, Parser
import tree_sitter_cpp as tscpp


CPP_LANGUAGE = Language(tscpp.language())


def parse_source(src: bytes) -> Node:
    parser = Parser(CPP_LANGUAGE)
    return parser.parse(src).root_node


def node_text(src: bytes, node: Node) -> str:
    return src[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def one_line(text: str, limit: int = 70) -> str:
    compact = " ".join(text.split())
    if len(compact) > limit:
        return compact[: limit - 3] + "..."
    return compact


def print_tree(node: Node, src: bytes, depth: int = 0, max_depth: int = 7) -> None:
    indent = "  " * depth
    text = one_line(node_text(src, node))
    print(f"{indent}{node.type} [{node.start_byte}, {node.end_byte}) {text!r}")
    if depth >= max_depth:
        if node.children:
            print(f"{indent}  ...")
        return
    for child in node.children:
        print_tree(child, src, depth + 1, max_depth)


def walk(node: Node):
    yield node
    for child in node.children:
        yield from walk(child)


def find_sink_input_statement(root: Node, src: bytes) -> Node:
    matches = [
        node
        for node in walk(root)
        if node.type == "expression_statement"
        and node_text(src, node).strip() == "sink(input);"
    ]
    if not matches:
        raise ValueError("could not find exact statement: sink(input);")
    if len(matches) > 1:
        raise ValueError(f"expected one sink(input); statement, found {len(matches)}")
    return matches[0]


def find_function_definition(root: Node, src: bytes, name: str) -> Node:
    for node in walk(root):
        if node.type == "function_definition":
            for child in walk(node):
                if child.type == "identifier" and node_text(src, child) == name:
                    return node
    raise ValueError(f"could not find function definition: {name}")


def line_indent(src: bytes, byte_offset: int) -> str:
    line_start = src.rfind(b"\n", 0, byte_offset) + 1
    line = src[line_start:byte_offset]
    return line.decode("utf-8", errors="replace")


def apply_edits(src: bytes, edits: list[tuple[int, int, bytes]]) -> bytes:
    buf = bytearray(src)
    for start, end, replacement in sorted(edits, key=lambda edit: edit[0], reverse=True):
        if start < 0 or end < start or end > len(buf):
            raise ValueError(f"invalid edit range: [{start}, {end})")
        print(f"edit [{start}, {end}) -> {replacement.decode('utf-8', errors='replace')!r}")
        buf[start:end] = replacement
    return bytes(buf)


def transform_chain(root: Node, src: bytes) -> bytes:
    target = find_sink_input_statement(root, src)
    indent = line_indent(src, target.start_byte)
    replacement = f"const char *tmp = input;\n{indent}sink(tmp);".encode("utf-8")
    return apply_edits(src, [(target.start_byte, target.end_byte, replacement)])


def transform_wrapper(root: Node, src: bytes) -> bytes:
    target = find_sink_input_statement(root, src)
    demo_func = find_function_definition(root, src, "demo")
    wrapper = (
        "static void wrapper(const char *x) {\n"
        "    sink(x);\n"
        "}\n\n"
    ).encode("utf-8")
    edits = [
        (demo_func.start_byte, demo_func.start_byte, wrapper),
        (target.start_byte, target.end_byte, b"wrapper(input);"),
    ]
    return apply_edits(src, edits)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Minimal tree-sitter playground for byte-offset C transforms."
    )
    ap.add_argument("source", type=Path)
    ap.add_argument("--mode", choices=["tree", "chain", "wrapper"], default="tree")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    src = args.source.read_bytes()
    root = parse_source(src)

    if args.mode == "tree":
        print_tree(root, src)
        target = find_sink_input_statement(root, src)
        print(
            f"\nfound exact statement at [{target.start_byte}, {target.end_byte}): "
            f"{node_text(src, target)!r}"
        )
        return

    if args.mode == "chain":
        output = transform_chain(root, src)
    else:
        output = transform_wrapper(root, src)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_bytes(output)
        print(f"wrote {args.out}")
    else:
        print(output.decode("utf-8", errors="replace"))


if __name__ == "__main__":
    main()

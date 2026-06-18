# tree-sitter playground

This is a minimal tree-sitter playground for C/C++ source-code transformations.
It demonstrates the pipeline we care about right now:

1. parse `toy.c`;
2. inspect the parse tree;
3. find one syntax node for the exact statement `sink(input);`;
4. replace source text with `node.start_byte` and `node.end_byte`;
5. write transformed C files.

The goal is not to build a full transformation framework. The goal is to make
the node and byte-offset mechanics easy to see.

## What tree-sitter is

tree-sitter is an incremental parsing library. Given source text and a grammar,
it builds a concrete syntax tree for the program. In this playground we use the
Python binding plus the `tree-sitter-cpp` grammar, which can parse this small C
example because C is largely a subset of C++ syntax.

## tree-sitter vs Comby

Comby is useful for quick structural search/replace demos. It is lightweight
and easy to explain, but it mainly works from code-shaped patterns.

tree-sitter gives us a parser-backed tree with node types and byte ranges. That
makes it easier to say "replace this exact statement node" instead of relying
only on a textual pattern. It is a better next step for syntax-level
transformations such as variable chains and wrapper calls.

tree-sitter is still not fully type-aware. It does not perform macro expansion,
does not resolve includes, and does not provide compiler semantics. It should
not be described as a replacement for CodeQL, Clang, or a full static-analysis
pipeline.

## AST, CST, node, and byte offset

An AST usually means an abstract syntax tree: a simplified representation of
program structure. A CST means a concrete syntax tree: a tree that keeps more of
the surface syntax, including punctuation and exact source spans.

tree-sitter returns syntax nodes. Each node has:

- `type`: the grammar node kind, such as `function_definition`,
  `call_expression`, or `expression_statement`;
- `start_byte`: the byte index where the node begins in the source file;
- `end_byte`: the byte index where the node ends in the source file.

This playground uses those byte offsets directly:

```python
buf[start_byte:end_byte] = replacement
```

If there are multiple edits, they are applied in reverse byte-offset order.
That avoids the classic offset-shift bug where an earlier edit changes the
positions of later edits.

## Commands

Install dependencies:

```bash
pip install "tree-sitter>=0.22" tree-sitter-cpp
```

Print the parse tree and the located node:

```bash
python ts_playground.py toy.c --mode tree
```

Create transformed files:

```bash
python ts_playground.py toy.c --mode chain --out outputs/toy_chain.c
python ts_playground.py toy.c --mode wrapper --out outputs/toy_wrapper.c
```

Compile the original and transformed files:

```bash
gcc -Wall -Wextra -c toy.c -o outputs/toy.o
gcc -Wall -Wextra -c outputs/toy_chain.c -o outputs/toy_chain.o
gcc -Wall -Wextra -c outputs/toy_wrapper.c -o outputs/toy_wrapper.o
```

## Expected transformations

`--mode chain` replaces:

```c
sink(input);
```

with:

```c
const char *tmp = input;
sink(tmp);
```

`--mode wrapper` inserts:

```c
static void wrapper(const char *x) {
    sink(x);
}
```

and replaces:

```c
sink(input);
```

with:

```c
wrapper(input);
```

# Notes: tree-sitter playground

## Conclusion

This playground shows the minimum useful tree-sitter transformation workflow:

1. parse C/C++ source with `tree-sitter-cpp`;
2. inspect syntax nodes and byte ranges;
3. find the exact `expression_statement` node for `sink(input);`;
4. replace source text using `node.start_byte` and `node.end_byte`;
5. apply multiple edits in reverse byte-offset order.

Compared with the Comby playground, tree-sitter gives a real parser-backed
syntax tree. That makes transformations less dependent on surface text patterns
and better suited for the next syntax-level stage of the research.

The important boundary is semantic: tree-sitter is not fully type-aware, does
not expand macros, and does not model compiler or CodeQL semantics. It is a
good syntax-level transformation layer, not a substitute for CodeQL or Clang.

## Demo transforms

- `chain`: rewrites `sink(input);` into a temporary variable chain.
- `wrapper`: inserts a wrapper function and rewrites `sink(input);` into
  `wrapper(input);`.

Both transforms preserve the main research message:

```text
parse tree -> find node -> byte offset replacement -> transformed C file
```

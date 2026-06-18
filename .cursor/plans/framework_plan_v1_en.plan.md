---
name: cpp srcml transform framework
overview: A modular, strict tree-to-tree C/C++ source transformation framework built on srcML (lossless XML round-trip) plus lxml. Candidate location, pick, tree rewriting, unparsing, validation, and JSONL batch processing/reporting are fully decoupled. The first version ships two transformations (variable_chain and macro_alias) to support downstream adversarial experiments against LLM- and CodeQL-based vulnerability detectors.
todos:
  - id: scaffold
    content: Create the cpp_transform package skeleton, requirements.txt (lxml), and README; implement the Frontend protocol and srcml_frontend (subprocess + lxml).
    status: completed
  - id: roundtrip
    content: srcML round-trip foundation (parse -> no change -> unparse); for sven_sample_10, record exact/normalized equality, reparse, compiler validation, and diff; language detection order is --language > field > extension, otherwise skipped/error.
    status: completed
  - id: model-locators
    content: Implement the Candidate/Context/Result models plus decl_locator and call_locator (XPath, read-only); CLI can dump candidates.
    status: completed
  - id: pick
    content: Implement pick strategies - first / random(seed) / all / one_per_function.
    status: completed
  - id: variable-chain
    content: Implement the variable_chain tree-to-tree transformation (snippet parse + graft, never byte editing); only primitives/enums/plain pointers, skipping class/struct/template/reference/array/aggregate/volatile/multi-declarator/global; with name-collision protection.
    status: completed
  - id: validation
    content: Implement validators - srcML reparse (required) + compiler abstraction (clang/clang++ preferred, gcc/g++ fallback, -fsyntax-only) + structural + applied checks + rollback.
    status: completed
  - id: macro-alias
    content: Implement macro_alias (preprocessor / round-trip demo) - unique macro name + whole-tree collision check + bare-callee restriction + insertion.
    status: completed
  - id: cli-file
    content: Implement the file subcommand - single file/function, with configurable transform/pick/seed/out.
    status: completed
  - id: batch-jsonl
    content: Implement the batch subcommand - streaming JSONL, field detection, per-record error isolation, per-transform/combined modes, original preservation + metadata.
    status: completed
  - id: report-tests
    content: Implement report (markdown + unified diff + summary) and run_log.jsonl; pytest coverage for round-trip/location/both transforms/collisions/batch isolation.
    status: completed
isProject: false
---

# C/C++ Tree-to-Tree Transformation Framework (srcML + lxml)

## Rationale
- Confirmed constraints: srcML may be installed; v1 must be **strict tree-to-tree** (parse -> mutate the structured tree -> unparse), with raw byte-offset editing prohibited.
- The existing prototype [adversarial_transform.py](C:\Users\TerryLu\Desktop\Transformation\adversarial_transform.py) and the two playgrounds all use "tree-sitter/Comby location + byte replacement," which does not satisfy strict tree-to-tree and serves only as reference.

## Toolchain
- Runtime: **WSL** runs srcML and the entire framework (srcml/clang/gcc invoked through WSL).
- Primary backend: the **srcML binary** (lossless parse/unparse, preserving comments/macros/preprocessor/formatting, no compile_commands required) + **lxml** (XPath location + subtree insert/delete/modify for true tree-to-tree) + subprocess.
- Validation: **compiler abstraction** - prefer `clang/clang++`, fall back to `gcc/g++`; srcML reparse is a **required** validation. A tree-sitter secondary check is **not part of v1** (deferred).
- tree-sitter/Comby are not chosen as the primary rewriter (byte editing only); Clang is not chosen as the v1 backend (requires compilation info, lossy pretty-printing, fragile on header-less snippets).

## STRICT Tree-to-Tree Hard Constraints (implementation red lines)
- **Prohibited**: implementing any transformation via byte-offset editing or by replacing whole source-string spans.
- All changes must mutate the **lxml/srcML structured tree**; the final source **must** be produced via `srcml --unparse`.
- The standard way to construct new nodes: **parse a small snippet** with srcML to obtain a subtree, then **graft** it into the appropriate location in the main tree (rather than hand-writing XML text or splicing into the source).
- Byte offsets are allowed only for **read-only** purposes (location/reporting/diff), never for generating output source.

## Modules / Directory
- `cpp_transform/frontends/`: `base.py` (Frontend protocol parse/unparse), `srcml_frontend.py`.
- `cpp_transform/model/`: `candidate.py`, `context.py` (tree/nsmap/name counter), `result.py`.
- `cpp_transform/locators/`: `base.py`, `decl_locator.py`, `call_locator.py`.
- `cpp_transform/pick/strategies.py`: first / random(seed) / all / one_per_function / by_confidence.
- `cpp_transform/transforms/`: `base.py` (ABC + REGISTRY + @register), `variable_chain.py`, `macro_alias.py`.
- `cpp_transform/codegen/unparse.py`, `validation/validators.py`, `io/dataset.py` + `writer.py`, `report/report.py`, `tests/`, `cli.py`.
- New-transform interface: `find_candidates / can_apply / apply (mutate XML in place) / structural_check` + `@register`.

## The Two v1 Transformations
- `variable_chain` (primary, a general data-flow transformation): `T x = E;` -> graft two decl_stmt nodes into the tree, `T __chain_x = E; T x = __chain_x;`; the type reuses the declaration's `<type>` subtree.
  - **Applied only to clearly safe simple types**: primitives (int/char/float/...), enums, plain pointers (`T*`).
  - **Skipped**: class/struct objects, template types, references (`T&`/`T&&`), arrays, aggregate (brace) initialization, `volatile`, multiple declarators, `static`/`extern` globals. Reason: an extra temporary could change C++ copy/move, destructor, and lifetime semantics.
  - `__chain_<name>` is deduplicated against all tree identifiers; on collision a numeric suffix is appended.
- `macro_alias` (the second, a **preprocessor / tree round-trip demo**, not a general data-flow transformation): for a bare-identifier callee memory call (e.g. `free`), graft a `<cpp:define>` with a unique macro name (e.g. `SAFE_FREE_<n>`) at a suitable place, rewrite the matched call `<name>`, and insert a `#undef` at the end of scope/file so the macro does not affect later code.
  - Constraints: unique macro name + whole-tree collision check; bare callee only (skip function pointers/member calls); type-agnostic, common to C/C++.
- **Next general data-flow transformation**: `array_indirection` (top pick for v2), followed by pointer indirection, wrapper_function (needs a type oracle in C), struct_field, func-ptr forwarding, dead-code.

## Language Detection (no silent default)
- Detection priority: explicit `--language` argument > dataset `language`/`lang` field > file extension.
- When none of the three resolves: **do not default to C/C++**; mark the record `skipped`/`error` and record the reason (the batch continues).

## Validation (layered, no overclaiming; compiler abstraction)
- syntax (required): srcML **reparse must pass**.
- compilation (compiler abstraction): prefer `clang/clang++`, fall back to `gcc/g++`, `-fsyntax-only` + a lenient preamble; header-less snippets are often N/A -> marked skipped (not a failure).
- structural: a transform-specific assertion; the applied check guards against no-ops.
- assumed-semantic / vulnerability: not formally proven, marked assumed, left for empirical CodeQL/LLM checking.
- On failure -> roll back to the original + record run_log.jsonl + continue the whole batch.

## Round-Trip Testing (no assumption that srcML is perfectly lossless)
For each snippet, record and report separately: **exact-text equality**, **normalized equality** (whitespace-normalized), whether **srcML reparse** succeeds, the **compiler validation** result, and a **unified diff**. We do not assume every snippet round-trips losslessly; we measure the fidelity rate empirically.

## Environment and Batch Defaults (confirmed)
- Runtime: **WSL**.
- batch by default transforms only `func_vuln`/`vuln_func`, with `--fields vuln|fixed|both`.
- Output defaults to **separate transform records** (one record per transform).
- When the language cannot be resolved, **do not default**; record a failure or require an explicit `--language`.

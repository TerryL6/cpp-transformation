---
name: transform framework v2 - source location
overview: Add a source-location tracking system to the existing srcML+lxml strict tree-to-tree C/C++ transformation framework. Begin with a feasibility study of srcML position behavior (no assumptions), then evaluate single-tree vs dual-tree designs before implementing location tracking. Record line/column for located/selected/before/after points and distinguish what a line number means across four input types (file, function, snippet, JSONL field), recovering the true repository position only when possible and never fabricating it. lxml remains the sole rewriting backend. Repository-level validation has been split out into V3. This phase produces a technical plan only; no code is changed.
todos:
  - id: srcml-position-study
    content: Feasibility study (no assumptions; run by the agent directly, leaving no tables or test files) - empirically test srcML --position start/end representation, 1-based/0-based, tab effect on columns, which node types carry positions, whether positions interfere with mutation/unparse, whether they go stale after a transform, and whether reparsing is required; report the findings verbally for your own judgment.
    status: completed
  - id: single-vs-dual-decision
    content: Decide between single-tree and dual-tree based on the study results; if dual-tree, implement "locate on the clean tree + position sidecar + structural index-path mapping"; capture positions eagerly into SourceLocation value objects at locate time.
    status: completed
  - id: location-model
    content: Implement the SourceLocation model with input/original/transformed/repo basis and mapping_status; fix source_location parsing (start+end); add a with_position option to the frontend.
    status: completed
  - id: location-flow
    content: Thread location information through locate/pick/transform/unparse/report; extend the output JSONL and report; define file/function/snippet/JSONL-field semantics and repository line-number recovery rules.
    status: completed
  - id: output-location-extension
    content: Extend TransformResult/run_log/report with the locations field and a location-recovery-rate summary.
    status: completed
isProject: false
---

# C/C++ Transformation Framework V2: Source-Location Tracking (Plan Only, No Implementation)

> Constraint compliance: this plan **does not modify any existing code**. lxml remains the default and only rewriting backend.
> Split note: this V2 **covers source-location tracking only**; repository-level compilation validation has been split out into **V3** (`framework_plan_v3_*`). V3's "locate the file and code position / reverse line-number mapping" depends on this V2 location model.

---

## 0. Implementation Status (✅ Done — 2026-06, incl. post-review simplification)

Implemented and passing all 36 tests. Decision: **Option A (single-tree)** — the feasibility study confirmed position attributes have **zero interference** with mutation/unparse, so no dual-tree is needed; `SourceLocation` is captured eagerly at locate time (before mutation).

**Final data model (simplified after review, 9 fields -> 6)**

- `SourceLocation` (6 fields): `source` (file path or JSONL field name), `relative_to` (`input` | `file` | `output` | `repo`), `start_line/start_col/end_line/end_col` (1-based).
  - Merged: old `basis` + `mapping_status` -> a single `relative_to`; renamed `path_or_field` -> `source`.
  - Dropped: `confidence` (dead field). Moved out: `tab_size` -> **run-level** (the `run_meta` line of `run_log.jsonl` + the report).
- `transform` block (flattened; the `locations` sub-block is gone):
  - `candidate_count`: total candidates located (selected + not).
  - `selected_candidates`: **slim** structured descriptions of the changed candidates (`cid`/`node_type`/`enclosing_function`/`original_text`/`source_location`); the **before location** is each candidate's `source_location` (precise, per candidate).
  - `transformed_location`: **after location = list of changed line ranges (Option B)**, from `changed_line_spans` line-diffing original vs. output, `relative_to=output`, columns unset; a pure deletion is a zero-width point.
- **De-duplication**: the old design stored the before location three times (`candidate`/`selected[0]`/`original`); it is now a single source of truth (each selected candidate's `source_location`).

**Per-file changes**

- **Added** [location/model.py](cpp_transform/location/model.py) + [__init__.py](cpp_transform/location/__init__.py): `SourceLocation`, `from_srcml_node()`, `apply_input_context()`, `changed_line_spans()`.
- **frontend**: `parse(..., with_position=False)`, appending `--position --tabs=N`; `tab_size` stays a frontend config (default 8).
- **pipeline**: parse with positions -> enrich before locations -> mutate -> unparse -> fill `candidate_count`/`selected_candidates`/`transformed_location`.
- **cli**: tag input semantics (`file`/`snippet`/`jsonl_field`); run_log gains `candidate_count`/`before_line`/`relative_to` and a run-level `tab_size` `run_meta` entry; combined mode aggregates.
- **report**: "Source locations" section (before/after coverage + `relative_to` distribution + `tab_size`).
- [io/writer.py](cpp_transform/io/writer.py) needed **no change**: serialized via `TransformResult.to_dict()`.

**Key semantics & settled questions**

- Input semantics: `file` input -> before `relative_to=file`; `function/snippet/jsonl_field` -> `relative_to=input` (**no fabricated** repo line numbers).
- **Repository line-number recovery (`relative_to=repo`) is deferred to V3** (needs the dataset's file/commit anchors; `line_changes.line_no` is function-relative — the gap V3 will close).
- After locations are line-level, intended for reports + V3 compile-error attribution; detector evaluation is repo/function level, so column-precise per-candidate after-positions are not needed.
- Settled: default `--tabs=8`; primary runtime is **WSL**; Option A has no sidecar performance concern.

---

## 1. Requirement

Record line/column for every transformation, covering four points: **located candidates / selected candidate / original code before transformation / generated code after transformation**; and distinguish what a "line number" means across four input types - file, function, snippet, and JSONL field. Recover the true repository position only when possible; **never fabricate** it when information is insufficient.

## 2. Relationship to the Existing Framework

- The existing pipeline is highly decoupled ([cpp_transform/pipeline.py](cpp_transform/pipeline.py) chains parse->locate->pick->transform->unparse->validate). [Candidate](cpp_transform/model/candidate.py) already has `source_location/confidence/metadata`, and [TransformResult](cpp_transform/model/result.py) already has an extensible `validation` dict. **Location tracking can be added as an "extension," not a rewrite.**
- **Key gap (the starting point for this requirement)**: `source_location()` in [locators/base.py](cpp_transform/locators/base.py) parses `pos:start`, but `parse()` in [frontends/srcml_frontend.py](cpp_transform/frontends/srcml_frontend.py) never passes `--position`, so positions are currently always `None`.
- **Key constraint (drives the single/dual-tree decision)**: transforms graft/insert/remove directly on `cand.node`, a **live lxml element** (see `apply` in [transforms/variable_chain.py](cpp_transform/transforms/variable_chain.py)). Therefore the candidate node must belong to the tree that is mutated and unparsed.
- Each record in `sven_sample_10.jsonl` contains `file_name / func_name / line_changes`, where `line_changes.line_no` is **function-relative** (counted from the function text's first line), not file-relative - precisely the mapping problem this V2 must clarify and formalize.
- Conclusion: add a `location/` subsystem plus minor extensions to frontend/pipeline/model/io/report.

## 3. srcML Position-Behavior Feasibility Study (run by the agent, no artifacts)

> Principle: **assume no behavior**. Documented facts (1-based, default tab=8, the `pos` namespace, the `L:C` colon format) are treated as **hypotheses to confirm**, verified empirically.
> Execution: I (the agent) run `srcml` directly on small throwaway inputs to perform this study, **producing no tables and leaving no test files in the repo**; afterward I **report the conclusions verbally** so you can make your own judgment.

Questions to test and answer:
- **start/end representation**: are `pos:start`/`pos:end` `line:col`; does end point at the element's last character or one past it?
- **1-based vs 0-based**: is the file's first token `1:1`?
- **tab effect on columns**: for a line containing `\t`, the column difference of the post-tab token under `--tabs=1` vs `--tabs=8`.
- **which node types carry positions**: does every element carry `pos:*`, or only some types?
- **do positions interfere with mutation/unparse**: unparse the position-bearing XML directly and diff against the original; graft into the position-bearing tree then unparse vs the same edit on a clean tree, byte-compared.
- **do they go stale after a transform**: after a graft, do surrounding `pos:*` still reflect old coordinates (expected: stale)?
- **is reparsing required**: re-parse the unparsed transformed source with `--position` and confirm fresh coordinates can be obtained.
- Extra: the inconsistency of a grafted subtree (parsed separately, positions relative to the snippet) once merged into the main tree.

The deliverable is the verbal conclusions to the above, serving as the factual basis for the Option A/B decision and subsequent design.

### Findings (2026-06, measured on WSL: srcml 1.1.0 / srcql 1.0.0 / lxml 6.1.1)

- **start/end representation**: `pos:start="line:col"` / `pos:end="line:col"` (colon-separated); **end is inclusive, pointing at the element's last character** (e.g. `int` -> `1:1`..`1:3`, `main` -> `1:5`..`1:8`); boundary nodes occasionally show column 0 (e.g. `block_content` `pos:end="3:0"`).
- **1-based**: both line and column are **1-based** (the first token `int` is `1:1`).
- **tab effect on columns**: confirmed - on a `\t`-indented line, the post-tab `int` is at column 2 under `--tabs=1` and column 9 under `--tabs=8`; default tab=8, recorded as `pos:tabs="8"` on `<unit>`.
- **which node types carry positions**: **nearly every element** carries `pos:start/end` (function/type/name/parameter_list/block/block_content/decl_stmt/decl/init/expr/literal, etc.), not just some types.
- **positions do not interfere with mutation/unparse**: position-bearing XML and clean XML unparse **byte-identically**; a real graft (inserting a position-bearing snippet subtree into a position-bearing tree) unparses correctly; `parse(--position) -> unparse` is **exactly lossless**. -> srcml unparsing **ignores position attributes**.
- **positions go stale after a transform**: after a graft the original node still claims old coordinates, and the snippet node carries snippet-relative (misplaced) coordinates.
- **reparse required**: re-parsing the transformed source with `--position` is needed for correct fresh coordinates (e.g. `z` -> `2:5`, `x` -> `3:5`).
- **incidental**: a file-path input leaks a `filename` attribute, whereas stdin (`-`) does not (the framework already uses stdin).
- **implication for the decision**: positions have **zero interference** with mutation/unparse, so **Option A (single-tree) is viable and simpler**; **Option A is the preliminary recommendation** (final call is yours).

## 4. Single-Tree vs Dual-Tree: Evaluation and Recommendation

> Do not auto-adopt dual-tree. Three upfront insights:
> 1. **Capture positions eagerly into `SourceLocation` value objects at locate time** (not relying on node `pos:*` attributes) -> whether attributes go stale after a transform no longer affects the recorded positions. Both options adopt this premise.
> 2. **lxml nodes are not interchangeable across trees**: two parses yield distinct objects; existing transforms mutate `cand.node` directly and **must not** be handed a node from another tree.
> 3. Therefore the mapping direction must guarantee `cand.node` belongs to the mutation tree.

**Option A - Single-tree (recommended default, premise: the study confirms positions do not interfere with mutation/unparse)**
- Parse once (with `--position`) -> locate -> capture positions eagerly -> mutate the same tree -> unparse.
- Pros: simplest; candidate identity is preserved for free; **zero change to locator/transform interfaces**; no mapping problem.
- Cons/risks: depends on "position attributes being harmless to unparse/graft" (expected, since srcml unparsing relies on element text, not position attributes); grafted subtrees have inconsistent positions, but since positions are captured eagerly and post-transform positions require a reparse anyway, the impact is zero.

**Option B - Corrected dual-tree (fallback, only if the study detects interference)**
- The locator still runs on the **clean mutation tree** (so `cand.node` is valid for transforms); separately parse a **read-only position sidecar tree**; for each candidate node, use its **structural index path** in the clean tree to resolve the same-path node in the sidecar, read `pos:*`, and write into `SourceLocation`.
- Pros: mutation/unparse identical to today, zero interference risk; zero transform-interface change (never hands a foreign node to a transform).
- Cons: one extra parse + a path-mapping helper; the pipeline/locator gains a "position enrichment" step.

**Candidate -> position mapping design (for Option B)**
- **Preferred: structural index path** - the per-level sequence of child-element indices from the root (e.g. `[0,3,1,2]`). Parsing the same source with/without positions yields **structurally isomorphic** trees (only extra attributes), so an index path resolves 1:1, **deterministically, collision-free**.
- **Guards**: `localname`/node-kind must match at each level; `normalized-text equality` is an assertion only (not the key).
- **Explicit**: never reuse an lxml node object from the other tree; only use the path to re-resolve a node in the target tree.
- Do not use text fingerprints or (function name + type) as the key (identical statements would collide).

**Recommendation**: **test first; default to Option A; fall back to Option B only if the study detects interference.** Both capture positions eagerly into `SourceLocation`.

## 5. Source-Location Tracking Design (data model)

- **Enable position annotation**: add `parse(..., with_position=False)` to the frontend; append `--position` (optionally `--tabs=N`) on demand, emitting `pos:start="L:C"`/`pos:end="L:C"`.
- **Fix parsing**: extend `source_location()` to parse both start and end (currently start only), colon-separated, tolerant of missing values.
- **Location metadata model `SourceLocation`** (new `cpp_transform/location/model.py`), fields:
  - `start_line/start_col/end_line/end_col` (all 1-based, per the study's conclusion);
  - `basis`: enum `input_relative | original_source | transformed_output | repo_relative`;
  - `path_or_field`: file path or JSONL field name;
  - `mapping_status`: `exact | input_only | repo_recovered | ambiguous | unknown`;
  - `confidence`, `tab_size`.
- **Position-invalidation rule**: after transform + unparse, the original positions become stale; if post-transform positions are needed, **re-parse the transformed source (with `--position`)** rather than reusing the old positions.

## 6. Position Semantics for File / Function / Snippet / JSONL Field

- **Complete file**: positions are **file-relative** and map directly to true repository line/column.
- **Extracted function / snippet**: positions are only **relative to the extracted input** (counted from the snippet's first line) and do not equal repository line numbers.
- **JSONL field**: positions are relative to **the code string stored in that field** (e.g. `func_vuln`); `path_or_field` must be recorded explicitly.
- **Whether the true repository position can be recovered**:
  - Yes: when a "field's starting line/character offset within the original file" mapping is available (e.g. the start line of `func_name` in `file_name` can be located, or the dataset provides a char offset), input-relative can be lifted to repo-relative with `mapping_status=repo_recovered`.
  - No: with only an isolated snippet and no file anchor, only input-relative is provided, `mapping_status=input_only`, and **repository line numbers are not fabricated**.
- Note that srcML column numbers depend on tabs (default tab=8, per the study), and historically multi-byte Unicode columns were off (fixed in 2025); record `tab_size` in the metadata for reproducibility.

## 7. Changes to the Existing Architecture and Data Models

- **Add** `cpp_transform/location/`: the `SourceLocation` model + (for Option B) a structural index-path mapping helper + (optionally) an input->repo mapper skeleton (the actual reverse mapping lands in V3).
- **Minor extensions** (no rewrite):
  - [frontends/srcml_frontend.py](cpp_transform/frontends/srcml_frontend.py): a `parse(..., with_position=False)` option (for Option B, plus a position-sidecar parse).
  - [locators/base.py](cpp_transform/locators/base.py): `source_location()` parses start+end and returns a `SourceLocation`; positions captured eagerly at locate time.
  - [model/candidate.py](cpp_transform/model/candidate.py): `source_location` switches to `SourceLocation`.
  - [model/result.py](cpp_transform/model/result.py): add a `locations` field (candidate/selected/original/transformed).
  - [pipeline.py](cpp_transform/pipeline.py): populate positions after locate; (optionally) re-parse the transformed source for post-transform positions; continue "isolate per-record failures, keep the batch going."
  - [io/writer.py](cpp_transform/io/writer.py) / [report/report.py](cpp_transform/report/report.py): extend output and reporting.
- Location-information flow: locate (input position, captured eagerly) -> pick (selected position) -> transform -> unparse -> (optional) re-parse the transformed source for post-transform positions -> report.

## 8. Output Metadata and Status

- New transform metadata: `locations`: `{candidate, selected, original, transformed}`, each a `SourceLocation` (with `basis` and `mapping_status`).
- Logs: `run_log.jsonl` gains location-summary fields; the report gains a "location-recovery rate" (distribution over `mapping_status`) summary.

## 9. Staged Implementation Plan and Dependencies

- **Phase 0 (feasibility study, no main-code changes)**: I run the Section 3 checks directly and report findings verbally (no tables or test files left behind).
- **Phase 1 (design decision)**: decide between Option A / Option B per the study; settle the `SourceLocation` model and the eager-capture strategy.
- **Phase 2 (must-do)**: location-tracking MVP - enable `--position`, fix `source_location`, the model, basis/mapping_status annotation; for Option B, implement the structural-path mapping.
- **Phase 3 (must-do)**: thread positions through locate/pick/transform/unparse/report, extend output JSONL and report, land the four-input-type semantics and repository line-number recovery rules.
- **Phase 4 (optional enhancement)**: enhanced input->repo line-number reverse mapping (reused by V3).
- **Dependencies**: Phase 0 -> 1 -> 2 -> 3; this V2 is a prerequisite for **V3 repository-level validation**'s "locate the file and code position."

## 10. Risks, Limitations, and Open Questions

- **Risks/limitations**: whether positions interfere with unparse/graft must be tested (it decides A/B); columns depend on tabs and multi-byte Unicode; the function-relative vs file-relative mapping gap of `line_changes.line_no`; field inconsistency across datasets.
- **Open questions for you to decide**:
  1. Default `--tabs` value (keep srcML's default 8, or fix at 1)?
  2. If Option B, parse a position sidecar tree for every record (performance vs information completeness)?
  3. Is the primary runtime **WSL** or native Windows (affects column/newline handling)?

## 11. Recommendation on What to Implement First

- **Do first**: Phase 0 (feasibility study) -> Phase 1 (single/dual-tree decision) - low risk, lets facts pick the design, and is a prerequisite for V3.
- Default to **Option A (single-tree)**; fall back to **Option B** only if the study detects position interference.
- Throughout, **lxml stays the default and untouched**; repository-level validation proceeds under **V3**.

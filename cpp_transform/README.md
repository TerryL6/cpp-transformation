# cpp_transform

A strict **tree-to-tree** C/C++ source transformation framework for studying how
general source-code transformations affect CodeQL and LLM-based vulnerability
detectors.

Source is parsed into a **srcML** XML tree, candidates are located, a pick
strategy selects them, the **structured tree is mutated** (via lxml, by grafting
parsed snippet subtrees), and source is regenerated **only** through srcML
`--unparse`. There is no byte-offset editing or source-string splicing.

```
source --srcml--> srcML XML tree --lxml mutate--> new tree --srcml--> source
                       |                                          |
                  locate + pick                              validate (reparse
                  candidates                                 + compiler + struct)
```

## Pipeline stages (decoupled)

| Stage | Module | In -> Out |
| --- | --- | --- |
| Frontend | `frontends/srcml_frontend.py` | code -> `<unit>` tree / tree -> code |
| Locate | `locators/` | tree -> `list[Candidate]` (read-only) |
| Pick | `pick/strategies.py` | candidates -> selected subset |
| Transform | `transforms/` | selected candidate -> mutated tree |
| Codegen | `codegen/unparse.py` | tree -> source |
| Validate | `validation/validators.py` | reparse / compiler / structural / applied |
| Dataset I/O | `io/` | streaming JSONL + language detection + writer |
| Report | `report/` | output JSONL -> markdown + diffs |

## v1 transformations

- **`variable_chain`** (`dataflow`): `T x = E;` -> `T __chain_x = E; T x = __chain_x;`.
  Only applied to **primitives, enums, and plain pointers**. Skips
  class/struct objects, templates, references, arrays, aggregate initializers,
  `volatile`, storage-class, and multiple declarators.
- **`macro_alias`** (`preprocessor`): a preprocessor / round-trip demo. Adds a
  unique `#define ALIAS free`, rewrites the bare callee, and inserts a matching
  `#undef`. Not a general data-flow transform; the next planned data-flow
  transform is `array_indirection`.

## Environment (WSL)

```bash
# Python deps
python3 -m pip install --user --break-system-packages lxml

# srcML (no-sudo local install example)
#   download srcml_*_ubuntu24.04_amd64.tar.gz, extract to ~/srcml,
#   then export the lib path:
export SRCML_BIN=$HOME/srcml/bin/srcml
export SRCML_LIB=$HOME/srcml/lib
"$SRCML_BIN" --version
```

## Command-line reference

The single entry point is `python3 -m cpp_transform.cli <subcommand> [options]`,
with three subcommands: `file` (single file/snippet), `batch` (JSONL dataset),
and `report` (render a report from output JSONL). A separate tool,
`python3 -m cpp_transform.tools.roundtrip_check`, audits round-trip fidelity.

Before running, configure srcML (see the Environment section above):

```bash
export SRCML_BIN=$HOME/srcml/bin/srcml   # path to the srcml executable
export SRCML_LIB=$HOME/srcml/lib         # LD_LIBRARY_PATH for srcml's libraries
```

Enumerated values:
- **transform names**: `variable_chain`, `macro_alias` (or `all` for every transform).
- **pick strategies**: `first` / `all` / `random` / `one_per_function`.

---

### 1) `file` — transform a single file or snippet

Reads one source file (or stdin), applies one or more transforms in sequence,
and writes to a file (or stdout).

```bash
# inspect candidates only, no changes
python3 -m cpp_transform.cli file --input foo.c --language C \
    --transform variable_chain --dump-candidates

# apply a single transform, write to a new file
python3 -m cpp_transform.cli file --input foo.c --language C \
    --transform variable_chain --out foo_adv.c

# apply several transforms in order, with compiler validation; print to stdout
python3 -m cpp_transform.cli file --input foo.c --language C \
    --transform variable_chain,macro_alias --pick all --compiler-validate
```

| Option | Value / default | Meaning |
| --- | --- | --- |
| `--input` | path / defaults to **stdin** | Input source file. If omitted, code is read from standard input. |
| `--language` | `C` or `C++` / default: inferred from file name | Force the language. With stdin (no `--input`) and no `--language`, the language cannot be inferred and the command exits with code 2. |
| `--transform` | name(s), comma-separated, or `all` / default `variable_chain` | Transform(s) to apply. Multiple ones are applied **sequentially** (each runs on the previous success's output). |
| `--pick` | `first`/`all`/`random`/`one_per_function` / default `first` | Candidate selection strategy (see "Pick strategies" below). |
| `--seed` | int / default `42` | Random seed for `random` and `one_per_function`, for reproducibility. |
| `--out` | path / defaults to **stdout** | Where the transformed source is written. |
| `--dump-candidates` | flag / default off | Print each transform's candidate list (JSON) and make **no changes**. Useful for debugging locators. |
| `--compiler-validate` | flag / default off | Also run a compiler syntax check (clang preferred, gcc fallback, `-fsyntax-only`). |
| `--srcml-bin` | path / default: env `SRCML_BIN` or `srcml` | Path to the srcml executable. |
| `--srcml-lib` | path / default: env `SRCML_LIB` | `LD_LIBRARY_PATH` needed to run srcml. |

Each transform's status (success/skipped/failed, whether it changed anything,
and the error reason) is printed to **stderr**; the transformed source goes to
stdout/`--out`.

---

### 2) `batch` — process a JSONL dataset

Streams a SVEN/PrimeVul-style JSONL, applies transforms to the chosen code
field(s), isolates per-record errors, and produces a transformed JSONL,
`run_log.jsonl`, and optionally a Markdown report.

```bash
# default: func_vuln field, all transforms, one separate record per transform
python3 -m cpp_transform.cli batch --jsonl sven_sample_10.jsonl \
    --out out/transformed.jsonl --transforms all --fields vuln \
    --mode separate --report out/report.md

# vuln + fixed fields, stack all transforms sequentially, with compiler check
python3 -m cpp_transform.cli batch --jsonl sven_sample_10.jsonl --out out/transformed.jsonl \
    --transforms variable_chain,macro_alias --fields both \
    --mode combined --compiler-validate --log out/run_log.jsonl

# quick look: stream pretty-printed records to stdout (no files written)
python3 -m cpp_transform.cli batch --jsonl sven_sample_10.jsonl --out - --pretty \
    --transforms variable_chain --fields vuln

# inspect only ONE input line (e.g. the 3rd record) and print its transform block:
python3 -m cpp_transform.cli batch --jsonl sven_sample_10.jsonl --out - --lines 3 \
    --transforms variable_chain --fields vuln 2>/dev/null | jq '.transform'

# inspect a few specific lines at once (1st, 3rd, 5th):
python3 -m cpp_transform.cli batch --jsonl sven_sample_10.jsonl --out - --lines 1,3,5 \
    --transforms variable_chain --fields vuln 2>/dev/null | jq '.transform.transformed_location'

# just the first N records (quick smoke test):
python3 -m cpp_transform.cli batch --jsonl sven_sample_10.jsonl --out - --limit 2 \
    --transforms variable_chain --fields vuln 2>/dev/null | jq '{field: .transform.target_field, changed: .transform.changed}'

# compare input vs output code for one line, side by side:
python3 -m cpp_transform.cli batch --jsonl sven_sample_10.jsonl --out - --lines 3 \
    --transforms variable_chain --fields vuln 2>/dev/null \
    | jq -r '"--- INPUT ---\n" + .func_vuln_original + "\n--- OUTPUT ---\n" + .func_vuln'
```

> `2>/dev/null` hides srcML's stderr noise so only the JSONL reaches `jq`. The
> `func_vuln_original` field holds the untouched input; `func_vuln` holds the
> transformed code (field names mirror whatever code field was transformed).

| Option | Value / default | Meaning |
| --- | --- | --- |
| `--jsonl` | path / **required** | Input JSONL dataset, one JSON record per line. |
| `--out` | path or `-`/`stdout` / **required** | Output path for the transformed JSONL (parent dirs auto-created). Use `-` or `stdout` to stream records to stdout instead of writing a file (handy for a quick look). |
| `--pretty` | flag / default off | Pretty-print (indent) the JSON. Most useful with `--out -`; with a file it just makes the JSONL multi-line. |
| `--lines` | comma-separated 1-based line numbers / default: all | Process only these input lines (matches the line number in the JSONL file). Great for inspecting one record's output, e.g. `--lines 3` or `--lines 1,3,5`. |
| `--limit` | int / default: all | Process only the first N records (quick smoke test / preview). |
| `--transforms` | name(s), comma-separated, or `all` / default `all` | Set of transforms to apply. |
| `--fields` | `vuln`/`fixed`/`both` / default `vuln` | Which code fields to transform. `vuln`→`func_vuln`/`vuln_func`; `fixed`→`func_fixed`/`fixed_func`; `both`→both. |
| `--mode` | `separate`/`combined` / default `separate` | `separate`: one record per (field × transform); `combined`: stack all transforms **sequentially** on the same field into one record. |
| `--pick` | `first`/`all`/`random`/`one_per_function` / default `first` | Candidate selection strategy. |
| `--seed` | int / default `42` | Random seed (reproducible). |
| `--language` | `C`/`C++` / default: inferred per record | Force the language for **all** records; otherwise inferred as `language field > file extension`. Records that cannot be resolved are marked `skipped` and the batch continues. |
| `--report` | path / default: none | Also generate a Markdown report (status summary + unified diffs). |
| `--log` | path / default: `run_log.jsonl` next to `--out` | Run-log path; one structured line per attempt (first line is a `run_meta` entry with the run-level `tab_size`). When `--out` is stdout, the run log is **skipped** unless `--log` is given explicitly. |
| `--compiler-validate` | flag / default off | Enable the compiler syntax-check layer. |
| `--srcml-bin` / `--srcml-lib` | same as `file` | srcml binary and library paths. |

**Output record schema** (separate mode): every original record field is kept,
and three things are added/replaced:
- `<field>` — replaced with the **transformed** code (e.g. `func_vuln`);
- `<field>_original` — the **original** code (e.g. `func_vuln_original`);
- `transform` — a metadata block describing the attempt.

The `transform` block looks like this:

```jsonc
"transform": {
  "name": "variable_chain",        // transform name ("a+b" / "combined" in combined mode)
  "family": "dataflow",
  "status": "success",             // success | skipped | failed
  "seed": 42,
  "target_field": "func_vuln",     // which field was transformed
  "language": "C",
  "changed": true,
  "error": null,                   // reason when skipped/failed (e.g. "no_candidates")

  "candidate_count": 3,            // total candidates located (selected + not)

  "selected_candidates": [         // the candidates actually changed (slim view)
    {
      "cid": "decl:0",
      "node_type": "decl_stmt",
      "enclosing_function": "compute",
      "original_text": "int x = a;",
      "source_location": {         // BEFORE location (precise, per candidate)
        "source": "func_vuln", "relative_to": "input",
        "start_line": 3, "start_col": 5, "end_line": 3, "end_col": 14
      }
    }
  ],

  "transformed_location": [        // AFTER: changed line ranges (diff hunks)
    { "source": "func_vuln", "relative_to": "output",
      "start_line": 3, "start_col": null, "end_line": 3, "end_col": null }
  ],

  "validation": {                  // each layer reported separately
    "srcml_reparse": { "status": "passed" },
    "structural":    { "status": "passed" },
    "applied":       { "status": "passed" },
    "compiler":      { "status": "passed" }   // only with --compiler-validate
  }
}
```

See [Source-location tracking](#source-location-tracking) for field meanings.
In **combined mode** the single `transform` block uses `family: "combined"`,
`validation.per_transform` (a per-transform status map), and `candidate_count` /
`selected_candidates` taken from the first transform that selected sites.

Alongside the output JSONL, `batch` writes `run_log.jsonl` (one line per attempt;
its first line is a `run_meta` entry recording the run-level `tab_size`).

stderr prints a summary: `in=` records read, `out_records=` records produced,
`skipped=`, `failed=`.

---

### 3) `report` — render a Markdown report from output JSONL

```bash
python3 -m cpp_transform.cli report --input out/transformed.jsonl \
    --out out/report.md --max-samples 20
```

| Option | Value / default | Meaning |
| --- | --- | --- |
| `--input` | path / **required** | Transformed JSONL produced by `batch`. |
| `--out` | path / **required** | Output path for the Markdown report. |
| `--max-samples` | int / default `10` | Number of leading before/after diff samples to show. |

Report contents: status counts per transform, srcML reparse pass rate, compiler
validation outcome distribution, a **Source locations** summary (before/after
coverage plus `basis` and `mapping_status` distributions), and unified diffs for
the first N samples.

---

### 4) `tools.roundtrip_check` — round-trip fidelity audit (no transform)

Runs only `parse → unparse` on each code field to measure srcML's lossless
round-trip rate (without assuming it is perfectly lossless).

```bash
python3 -m cpp_transform.tools.roundtrip_check --jsonl sven_sample_10.jsonl \
    --fields both --out out/roundtrip.jsonl --compiler-validate
```

| Option | Value / default | Meaning |
| --- | --- | --- |
| `--jsonl` | path / **required** | Input JSONL. |
| `--fields` | `vuln`/`fixed`/`both` / default `both` | Which code fields to audit. |
| `--out` | path / default: none | Per-(record × field) metrics JSONL (exact/normalized/reparse/diff). |
| `--language` | `C`/`C++` / default: inferred per record | Force the language. |
| `--compiler-validate` | flag / default off | Also run compiler validation. |
| `--srcml-bin` / `--srcml-lib` | same as above | srcml binary and library paths. |

stderr prints a summary: total / exact / normalized / reparse_ok counts.

---

### Pick strategies

| Strategy | Meaning |
| --- | --- |
| `first` | Pick the first candidate (default; deterministic, minimal change). |
| `all` | Select every candidate and apply to each (transform as many sites as possible). |
| `random` | Pick one random candidate using `--seed` (reproducible). |
| `one_per_function` | At most one candidate per function (first in the function when `--seed` is unset, otherwise random). |

### Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Success (in batch, a single failed record does not change the exit code; it is isolated and recorded in `run_log.jsonl`). |
| `2` | `file` could not resolve the language (no `--language` and no inferable file name). |

## Source-location tracking

Every transform records **where** the code it touched lives. The main tree is
parsed with srcML `--position`, and each candidate's line/column span is captured
**eagerly at locate time** (frozen into a value object), because srcML position
attributes go stale once the tree is mutated. This uses a single tree (no
separate "position tree"); the feasibility study confirmed position attributes do
not affect unparsing.

Two kinds of location are recorded:

- **Before** — where each *selected* candidate sat in the input. Read straight
  from srcML positions, so it is **precise (line + column), one per candidate**.
  Lives inside each entry of `selected_candidates` as its `source_location`.
- **After** — where the change landed in the regenerated code. Positions can't be
  read from the mutated tree, so this is derived by **line-diffing** the original
  vs. transformed source. It is a **list of changed line ranges** (line-level
  only, columns `null`), in `transformed_location`.

The before location is also visible per-candidate via `file --dump-candidates`.

### `SourceLocation` fields (6)

| Field | Meaning |
| --- | --- |
| `source` | Where the code came from: a file path (file input) or a JSONL field name like `func_vuln`. |
| `relative_to` | Which coordinate system the numbers are in (see below). |
| `start_line` / `start_col` | Start of the span, both **1-based**. |
| `end_line` / `end_col` | End of the span (inclusive). Columns are `null` for `transformed_location` (line-level only). |

**`relative_to`** — the coordinate system:

| Value | Meaning |
| --- | --- |
| `input` | Relative to the extracted snippet/field handed in (line 1 = its first line); no repo anchor. |
| `file` | Relative to a concrete file given as input — a real file location. |
| `output` | Relative to the transformed output (used by `transformed_location`). |
| `repo` | Lifted to a real repository file. **Reserved for V3**; not produced yet. |

### What you get per input type

| Input | before `relative_to` |
| --- | --- |
| `file --input foo.c` | `file` |
| `file` via stdin (snippet) | `input` |
| `batch` JSONL field (e.g. `func_vuln`) | `input` |

Recovering true **repository** line numbers from a function/field (using the
dataset's file/commit anchors) is intentionally deferred to **V3**. Note also
that `line_changes.line_no` in SVEN-style datasets is *function-relative*, which
is exactly the gap V3's reverse mapping will close.

**Notes**
- `tab_size` is a run-level constant (default 8), not repeated on every location;
  it is recorded once in `run_log.jsonl`'s `run_meta` line and in the report.
- `transformed_location` is a transform-agnostic line diff, so it reports changed
  **line ranges** only. A pure deletion is recorded as a zero-width point. Column-
  precise after-positions would require reparsing the output (possible future add).

## Validation layers (kept separate, not conflated)

- **syntax**: srcML reparse of the output (required).
- **structural**: transform-specific assertion + "applied" check.
- **compilation**: clang/clang++ preferred, gcc/g++ fallback (`-fsyntax-only`);
  isolated snippets that cannot compile are reported `skipped`, not `failed`.
- **assumed semantic / vulnerability preservation**: assumed by construction,
  to be checked empirically later with CodeQL / LLM detectors (not proven here).

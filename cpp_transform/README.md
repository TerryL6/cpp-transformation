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
| Anchor (opt) | `anchor/` | inject `va:id` before transform, recover after (V4) |
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
| `--repo-validate` | flag / default off | After a successful transform, run **repository-level compilation validation** (V3): clone/checkout the real repo, plug the transformed function back, and build. See [below](#repository-level-compilation-validation-v3). |
| `--repo-cache` | path / default `~/.cache/cpp_transform/repos` | Where full clones are cached (one per repo, reused across runs). |
| `--repo-build-timeout` | int seconds / default `600` | Per-command build timeout. Large repos (e.g. FFmpeg) may need a higher value. |
| `--repo-log-dir` | path / default: none | Directory to write combined baseline+transformed build logs (one file per record). |
| `--track-anchor` | flag / default off | Track **vulnerability anchors** (V4): inject a durable `va:id` from the record's `line_changes`, then after the transform report whether the vuln node survived and where it landed. See [below](#vulnerability-anchoring-v4). |
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

  "validation": {                  // SNIPPET-level checks (each layer separate)
    "srcml_reparse": { "status": "passed" },
    "structural":    { "status": "passed" },
    "applied":       { "status": "passed" },
    "compiler":      { "status": "passed" }   // only with --compiler-validate
  },

  "repo_validation": {             // WHOLE-REPO build (only with --repo-validate);
    "project": "FFmpeg",           // sibling of validation, NOT nested inside it
    "commit": "a7e032a...",        // record's commit_id (the FIX commit)
    "checkout_revision": "a7e032a...^1",   // parent (vulnerable) for func_vuln
    "commit_sha": "2b46ebd...",    // resolved 40-char SHA
    "file": "libavformat/rmdec.c",
    "func": "rm_read_multi",
    "recipe": "FFmpeg",            // override name or detected (cmake/autotools/make)
    "matched_span": { "file": "libavformat/rmdec.c", "start_line": 491, "end_line": 530 },
    "build_log_ref": "out/.../rmdec.c..._func_vuln.log",  // only with --repo-log-dir
    "status": "passed",            // see the V3 status enum
    "baseline_status": "passed",   // build of the UNMODIFIED checkout
    "mapping_status": "exact",     // how the function was matched (exact|normalized)
    "detail": null                 // extra reason for non-passed / edge cases
  },

  "vuln_anchor": [                 // VULN ANCHORING (only with --track-anchor);
    {                              // sibling of validation/repo_validation
      "id": "VA1",                 // stable anchor identity
      "role": "sink",
      "before": {                  // where the vuln node sat BEFORE (input coords)
        "source": "func_vuln", "relative_to": "input",
        "start_line": 34, "start_col": 9, "end_line": 35, "end_col": 53
      },
      "after": {                   // where it landed AFTER (output coords), or null
        "source": "func_vuln", "relative_to": "output",
        "start_line": 34, "start_col": null, "end_line": 35, "end_col": null
      },
      "status": "tracked",         // tracked | lost | ambiguous | not_attempted
      "detail": null
    }
  ]
}
```

> `repo_validation` is present only when `--repo-validate` is passed; see
> [Repository-level compilation validation (V3)](#repository-level-compilation-validation-v3)
> for the full field reference and status enum.

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

## Repository-level compilation validation (V3)

The lightweight validators above check a **snippet** in isolation. V3 adds a
stronger, optional check: does the transformed function still compile **inside
its real project**? It is enabled per `batch` run with `--repo-validate` and
runs only after a transform succeeds and actually changes code.

### What it does (per record)

1. **Metadata** — read `project` / `project_url` / `commit_id` / `file_name` /
   `func_name` from the record.
2. **Provision** — clone the repo **once** into the cache
   (`--repo-cache`), then create an isolated **git worktree** for this record so
   edits never touch the cache or other records.
3. **Checkout** — for `func_vuln` we check out the **parent** of the fix commit
   (`commit_id^1`, the vulnerable revision); for `func_fixed` we check out
   `commit_id` itself. (SVEN convention: `commit_id` is the *fix* commit.)
4. **Baseline build** — build the unmodified checkout first. Its result is the
   reference point.
5. **Placement** — locate the original whole function in `file_name` and replace
   it with the transformed function. A non-unique / fuzzy match is **not**
   patched (reported `skipped_ambiguous`).
6. **Transformed build** — rebuild (incremental) and compare to the baseline.
7. **Classify & log** — emit a status and, with `--repo-log-dir`, write the
   combined baseline+transformed build output.

Why a baseline: it separates *"the repo never built here in the first place"*
from *"the transform broke it"* — only the latter is a real regression.

### Status enum (`repo_validation.status`)

| Status | Meaning |
| --- | --- |
| `passed` | Baseline built **and** the transformed tree built. The real win. |
| `failed` | Baseline built but the transformed tree failed → **transform-introduced regression**. |
| `baseline_failed` | The unmodified checkout did not build in this environment; nothing is attributed to the transform. |
| `skipped_ambiguous` | The function could not be uniquely located in the file; no patch applied. |
| `skipped_no_repo` | Missing/unsupported repo metadata. |
| `environment_error` | No usable build recipe, or a git/clone/tooling failure. |
| `timeout` | A build command exceeded `--repo-build-timeout`. |
| `not_attempted` | Transform did not change code, so repo validation was skipped. |

### The `repo_validation` block

The full result is attached as **`transform.repo_validation`** — a **sibling of
`transform.validation`**, not nested inside it (`validation` = snippet-level
checks; `repo_validation` = whole-repository build). Inspect it with
`jq '.transform.repo_validation'`. Example:

```jsonc
"repo_validation": {
  "project": "FFmpeg",
  "commit": "a7e032a277452366771951e29fd0bf2bd5c029f0",
  "checkout_revision": "a7e032a277452366771951e29fd0bf2bd5c029f0^1",
  "commit_sha": "2b46ebdbff1d8dec7a3d8ea280a612b91a582869",
  "file": "libavformat/rmdec.c",
  "func": "rm_read_multi",
  "recipe": "FFmpeg",
  "matched_span": { "file": "libavformat/rmdec.c", "start_line": 491, "end_line": 530 },
  "build_log_ref": "out/ffmpeg_demo_logs/github.com_FFmpeg_FFmpeg_a7e032a27745_func_vuln.log",
  "status": "passed",
  "baseline_status": "passed",
  "mapping_status": "exact",
  "detail": null
}
```

| Field | Meaning |
| --- | --- |
| `project` | Project name from the record. |
| `commit` | The record's `commit_id` (SVEN convention: the **fix** commit). |
| `checkout_revision` | The revision actually checked out: `commit_id^1` (parent, vulnerable) for `func_vuln`, `commit_id` for `func_fixed`. |
| `commit_sha` | The concrete 40-char SHA that `checkout_revision` resolved to (added once provisioning succeeds). |
| `file` | Target source file (`file_name`) the function lives in. |
| `func` | Target function name (`func_name`) that was replaced. |
| `recipe` | Build recipe used: an override name (e.g. `FFmpeg`, `oniguruma`) or a detected one (`autotools` / `cmake` / `make`); `null` if none was found. |
| `matched_span` | Where the function was located **and replaced** in `file`: `{file, start_line, end_line}` (1-based, repo coordinates). `null` if it was never placed (baseline failed / ambiguous / skipped). |
| `build_log_ref` | Path to the combined baseline+transformed build log (only when `--repo-log-dir` is set); else `null`. |
| `status` | Final outcome — one of the [status enum](#status-enum-repo_validationstatus) values above. |
| `baseline_status` | Build result of the **unmodified** checkout: `passed` / `failed` / `timeout` / `error`, or `null` if a build was never started. |
| `mapping_status` | How the function was matched for placement: `exact` (byte-for-byte) or `normalized` (trailing-whitespace-insensitive); `null` if not placed. |
| `detail` | Extra reason text for non-`passed` / edge cases, e.g. `baseline_failed`, `transformed_stage=build[1]`, `merge_commit`, `no_build_system`, `baseline_timeout`. `null` when there is nothing to add. |

The report also adds a **Repository validation** outcome count.

### Build recipes (auto-detect first, declarative fallback)

A recipe is `setup` commands (configure / cmake) then `build` commands (make),
each an argv list run without a shell. Resolution order:

1. **Per-project override** — a small declarative table in
   `cpp_transform/repo/recipes.py` (`RECIPE_OVERRIDES`) for repos whose build
   quirks cannot be auto-detected. Adding a repo is **one row**, e.g. FFmpeg:
   `./configure --disable-asm` then `make` (the flag drops the nasm/yasm and old
   x86 inline-asm requirements so it builds C-only, no sudo).
2. **Auto-detection** — otherwise detected from marker files: `configure` /
   `autogen.sh` / `configure.ac` (autotools) → `CMakeLists.txt` (cmake) → a
   top-level `Makefile`. Unknown build systems yield `environment_error`.

### Example (worked, real)
```bash
export SRCML_BIN=$HOME/srcml/bin/srcml SRCML_LIB=$HOME/srcml/lib
python3 -m cpp_transform.cli batch --jsonl sven_sample_10.jsonl --out - --lines 9 \
    --transforms variable_chain --fields vuln \
    --repo-validate --repo-build-timeout 2400 \
    2>/dev/null | jq '.transform.repo_validation'
```

```bash
export SRCML_BIN=$HOME/srcml/bin/srcml SRCML_LIB=$HOME/srcml/lib
python3 -m cpp_transform.cli batch --jsonl sven_sample_10.jsonl --lines 9 \
    --transforms variable_chain --fields vuln \
    --repo-validate --repo-build-timeout 2400 \
    --out out/ffmpeg_demo.jsonl --log out/ffmpeg_demo_run_log.jsonl \
    --report out/ffmpeg_demo_report.md --repo-log-dir out/ffmpeg_demo_logs
```

Record 9 is FFmpeg `rm_read_multi` in `libavformat/rmdec.c`. `variable_chain`
rewrites `int number_of_streams = avio_rb16(pb);` into a two-step chain; the
modified function is plugged back at the parent commit; baseline builds, the
transformed tree builds → `repo_validation = passed`.

> Requirements: a working build toolchain (gcc/make, plus cmake for cmake repos)
> and network access for the initial clone. No Docker is used in V3 phases 1–4;
> WSL is the reference environment.

## Vulnerability anchoring (V4)

The evaluation loop is: run a detector on the original code (ground-truth vuln
location known) → transform → re-run the detector. That only makes sense if we
still know **where the vulnerability went**. V4 gives each vulnerable point a
**durable identity that survives transformation**.

### How it works

After parsing (with `--position`), we attach a custom namespaced attribute
`va:id="VA1"` to the smallest enclosing **statement node** of a vulnerable line —
exactly analogous to srcML's `pos:start`/`pos:end`, but authored by us in the
lxml layer. The attribute lives **only in the XML tree**; srcML's `--unparse`
emits source from element text and ignores unknown namespaced attributes, so
`va:*` **never appears in the emitted C/C++** and cannot pollute code or affect a
downstream detector (the same reason `pos:*` never leaks; confirmed by a test).

- **Injection** — the anchored line comes from the record's `line_changes`
  (`func_vuln` → the fix-*deleted* lines; `func_fixed` → the *added* lines).
  `line_changes[*].line_no` is function-relative, so it maps directly onto the
  extracted-function tree.
- **Propagation** — any transform that removes/replaces/regenerates a node must
  carry `va:*` onto the surviving node (`carry_anchor` in `transforms/base.py`).
  `variable_chain` does this: it pins the anchor onto the primary sink (the
  declaration that still holds the value). A plain move needs nothing.
- **Recovery** — after the transform we XPath `va:id` on the mutated tree. To get
  the *new* line span (srcML `pos:*` go stale after mutation) we probe a
  throwaway deep copy: glue a unique comment token at the anchored node, unparse,
  read the token's line, discard the copy (the emitted output is untouched).

> **Anchor ≠ candidate.** The framework's locators find *transformation
> candidates* (safe-to-rewrite patterns); the *vulnerability anchor* is the real
> vulnerable point from ground truth. They may sit at different lines.

### Status enum (`vuln_anchor[*].status`)

| Status | Meaning |
| --- | --- |
| `tracked` | Exactly one node still carries the anchor → clean before → after mapping. |
| `lost` | Zero surviving nodes → the vulnerable node may be gone (red flag). |
| `ambiguous` | More than one surviving node → a legit split we do not resolve by guessing. |
| `not_attempted` | Anchoring was requested but the line matched no statement node, or recovery never ran. |

### The `vuln_anchor` block

Attached as **`transform.vuln_anchor`** — a **sibling** of `transform.validation`
(snippet checks) and `transform.repo_validation` (repo build), never nested
inside them. It is a **list**, one entry per anchor. Each entry has six fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `id` | string | Stable anchor identity assigned at injection (`VA1`, `VA2`, …), in ascending order of the anchored line. It is what XPath looks for after the transform; the same `id` links the `before` and `after` positions. |
| `role` | string / null | A tag for what the anchored node is, for reporting only (currently always `"sink"`). Reserved for future roles (e.g. `source`, `guard`). |
| `before` | [`SourceLocation`](#sourcelocation-fields-6) / null | Where the vulnerable node sat **before** the transform, read eagerly from srcML `pos:*`. Precise (line + column). `relative_to` is `input` for a JSONL field / snippet, `file` for a real file. `null` only if the node had no position. |
| `after` | [`SourceLocation`](#sourcelocation-fields-6) / null | Where the anchor **landed after** the transform, recovered via the marker probe. Line-level only (`start_col`/`end_col` are `null`), `relative_to = output`. `null` when `status` is `lost` or `not_attempted`. |
| `status` | enum | Survival outcome — one of the [status enum](#status-enum-vuln_anchorstatus) values (`tracked` / `lost` / `ambiguous` / `not_attempted`). |
| `detail` | string / null | Extra reason for non-`tracked` / edge cases, e.g. `no statement node covers line N` when injection failed. `null` when there is nothing to add. |

> The whole `vuln_anchor` block is **omitted** (the field is absent, not `null`)
> when anchoring produced no requests at all — see the line-selection rule below.

### Which lines get anchored

The anchored lines come from the record's `line_changes` (the fix diff),
interpreted per target field:

| Field | Anchored lines | Rationale |
| --- | --- | --- |
| `func_vuln` | the fix-**deleted** lines (`line_changes.deleted[*].line_no`) | those are the lines that existed in the vulnerable version and the fix removed/changed — i.e. the vulnerable statements. |
| `func_fixed` | the fix-**added** lines (`line_changes.added[*].line_no`) | the added lines exist only in the fixed version. |

`line_no` is **function-relative** (line 1 = the function's first line), so it
maps directly onto the extracted-function tree. Each target line is resolved to
its smallest enclosing statement node.

> **Pure-addition fixes have no `func_vuln` anchor.** If a fix only *adds* lines
> (e.g. inserts a bounds check) and deletes nothing, there are no deleted lines,
> so `func_vuln` gets no anchor and its `vuln_anchor` block is omitted. This is
> expected, not a bug: there is no specific deleted statement to anchor in the
> vulnerable version. (In `sven_sample_10.jsonl`, records 1–3 are pure-addition
> fixes and therefore carry no `func_vuln` anchor.)

### Try it (worked, real — fast, no repo build)

Record 9 is FFmpeg `rm_read_multi`. Its `line_changes` marks function-relative
line 35 (`... size2, mime);`, which the fix changed to `NULL`) — a **different**
line from the `variable_chain` candidate on line 4:

```bash
export SRCML_BIN=$HOME/srcml/bin/srcml SRCML_LIB=$HOME/srcml/lib
python3 -m cpp_transform.cli batch --jsonl sven_sample_10.jsonl --out - --lines 9 \
    --transforms variable_chain --fields vuln --track-anchor \
    2>/dev/null | jq '.transform.vuln_anchor'
```

Expected: one `VA1` block with `status: "tracked"`, `before` at lines 34–35 and
`after` at lines 34–35 (`variable_chain` keeps its two new declarations on one
line, so no line shift). This proves the anchor is injected on the true
vulnerable statement, survives a real transform applied elsewhere, and is
re-located afterwards.

Anchoring is orthogonal to repo validation, so you can combine them
(`--track-anchor --repo-validate`) to get both a build result and a survival
status in the same record. Cross-file moves and multi-anchor records are
deferred (phase 6).

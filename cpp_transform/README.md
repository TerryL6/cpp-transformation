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
python3 -m cpp_transform.cli batch --jsonl data.jsonl --out out/t.jsonl \
    --transforms variable_chain,macro_alias --fields both \
    --mode combined --compiler-validate --log out/mylog.jsonl
```

| Option | Value / default | Meaning |
| --- | --- | --- |
| `--jsonl` | path / **required** | Input JSONL dataset, one JSON record per line. |
| `--out` | path / **required** | Output path for the transformed JSONL (parent dirs auto-created). |
| `--transforms` | name(s), comma-separated, or `all` / default `all` | Set of transforms to apply. |
| `--fields` | `vuln`/`fixed`/`both` / default `vuln` | Which code fields to transform. `vuln`→`func_vuln`/`vuln_func`; `fixed`→`func_fixed`/`fixed_func`; `both`→both. |
| `--mode` | `separate`/`combined` / default `separate` | `separate`: one record per (field × transform); `combined`: stack all transforms **sequentially** on the same field into one record. |
| `--pick` | `first`/`all`/`random`/`one_per_function` / default `first` | Candidate selection strategy. |
| `--seed` | int / default `42` | Random seed (reproducible). |
| `--language` | `C`/`C++` / default: inferred per record | Force the language for **all** records; otherwise inferred as `language field > file extension`. Records that cannot be resolved are marked `skipped` and the batch continues. |
| `--report` | path / default: none | Also generate a Markdown report (status summary + unified diffs). |
| `--log` | path / default: `run_log.jsonl` next to `--out` | Run-log path; one structured line per attempt. |
| `--compiler-validate` | flag / default off | Enable the compiler syntax-check layer. |
| `--srcml-bin` / `--srcml-lib` | same as `file` | srcml binary and library paths. |

**Output record schema** (separate mode): keeps all original record fields and adds:
- `<field>` replaced with the transformed code;
- `<field>_original` holding the original code;
- `transform` metadata (name/family/status/seed/language/changed/candidate/validation/error).

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
validation outcome distribution, and unified diffs for the first N samples.

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

## Validation layers (kept separate, not conflated)

- **syntax**: srcML reparse of the output (required).
- **structural**: transform-specific assertion + "applied" check.
- **compilation**: clang/clang++ preferred, gcc/g++ fallback (`-fsyntax-only`);
  isolated snippets that cannot compile are reported `skipped`, not `failed`.
- **assumed semantic / vulnerability preservation**: assumed by construction,
  to be checked empirically later with CodeQL / LLM detectors (not proven here).

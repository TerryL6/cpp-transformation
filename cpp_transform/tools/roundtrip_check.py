"""Round-trip audit: parse->unparse every code field in a JSONL and record
fidelity metrics, without assuming srcML is perfectly lossless.

For each (record, field) it records: exact-text equality, normalized equality,
srcML reparse success, and optional compiler validation; plus a per-record diff
when not exact. Writes a JSONL of per-item metrics and prints a summary.

Usage:
    python -m cpp_transform.tools.roundtrip_check --jsonl sven_sample_10.jsonl \
        --fields both --out out/roundtrip.jsonl [--compiler-validate]
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
from collections import Counter
from pathlib import Path

from ..frontends.srcml_frontend import SrcmlFrontend
from ..io.dataset import detect_code_fields, detect_language, iter_jsonl
from ..validation.validators import CompilerValidator, roundtrip_metrics


def _diff(a: str, b: str) -> str:
    return "\n".join(
        difflib.unified_diff(a.splitlines(), b.splitlines(), lineterm="")
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="roundtrip_check")
    ap.add_argument("--jsonl", required=True)
    ap.add_argument("--fields", choices=["vuln", "fixed", "both"], default="both")
    ap.add_argument("--out", help="write per-item metrics JSONL here")
    ap.add_argument("--language", help="force C/C++")
    ap.add_argument("--compiler-validate", action="store_true")
    ap.add_argument("--srcml-bin", default=None)
    ap.add_argument("--srcml-lib", default=None)
    args = ap.parse_args(argv)

    frontend = SrcmlFrontend(srcml_bin=args.srcml_bin, lib_path=args.srcml_lib)
    items: list[dict] = []
    summary = Counter()

    for it in iter_jsonl(args.jsonl):
        if it.error:
            summary["bad_json"] += 1
            continue
        record = it.record
        decision = detect_language(record, explicit=args.language)
        for field in detect_code_fields(record, which=args.fields):
            code = record[field]
            summary["total"] += 1
            if decision.language is None:
                summary["language_unresolved"] += 1
                items.append({
                    "lineno": it.lineno, "field": field,
                    "language": None, "reason": decision.reason,
                })
                continue
            m = roundtrip_metrics(frontend, code, decision.language)
            if m["exact_equal"]:
                summary["exact"] += 1
            if m["normalized_equal"]:
                summary["normalized"] += 1
            if m["reparse_ok"]:
                summary["reparse_ok"] += 1
            entry = {
                "lineno": it.lineno, "field": field,
                "language": decision.language, **m,
            }
            if args.compiler_validate and m["exact_equal"] is not None:
                cv = CompilerValidator(decision.language)
                entry["compiler"] = cv.validate(code, code)
                summary[f"compiler_{entry['compiler']['status']}"] += 1
            if not m["exact_equal"]:
                try:
                    restored = frontend.unparse(
                        frontend.parse(code, decision.language)
                    )
                    entry["diff"] = _diff(code, restored)
                except Exception as exc:  # pragma: no cover
                    entry["diff_error"] = str(exc)
            items.append(entry)

    if args.out:
        p = Path(args.out)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8") as fh:
            for e in items:
                fh.write(json.dumps(e, ensure_ascii=False) + "\n")

    print(json.dumps(dict(summary), indent=2), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

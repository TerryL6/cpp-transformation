"""Command-line interface: file / batch / report subcommands.

Examples
--------
    python -m cpp_transform.cli file --input foo.c --language C \\
        --transform variable_chain --pick first --out foo_adv.c

    python -m cpp_transform.cli batch --jsonl sven_sample_10.jsonl \\
        --out out/transformed.jsonl --transforms all --fields vuln \\
        --mode separate --report out/report.md

    python -m cpp_transform.cli report --input out/transformed.jsonl \\
        --out out/report.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import transforms as _transforms  # noqa: F401  (populates REGISTRY)
from .frontends.srcml_frontend import SrcmlFrontend
from .io.dataset import detect_code_fields, detect_language, iter_jsonl
from .io.writer import RunLog, build_output_record, write_jsonl
from .location.model import apply_input_context, changed_line_spans
from .model.context import TransformContext
from .pipeline import apply_transform
from .report import generate_report
from .transforms.base import REGISTRY, get_transform


def make_frontend(args) -> SrcmlFrontend:
    return SrcmlFrontend(srcml_bin=args.srcml_bin, lib_path=args.srcml_lib)


def add_frontend_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--srcml-bin", default=None, help="path to srcml (env SRCML_BIN)")
    p.add_argument("--srcml-lib", default=None, help="LD_LIBRARY_PATH for srcml (env SRCML_LIB)")


def resolve_transforms(spec: str) -> list[str]:
    if spec == "all":
        return sorted(REGISTRY)
    names = [s.strip() for s in spec.split(",") if s.strip()]
    for n in names:
        get_transform(n)  # validates / raises
    return names


def _first_before(selected_candidates: list[dict]) -> dict:
    """The BEFORE source_location of the first selected candidate (or {})."""
    if not selected_candidates:
        return {}
    return selected_candidates[0].get("source_location") or {}


# -- file ------------------------------------------------------------------
def cmd_file(args) -> int:
    frontend = make_frontend(args)
    if args.input:
        code = Path(args.input).read_text(encoding="utf-8")
        file_name = args.input
    else:
        code = sys.stdin.read()
        file_name = None

    decision = detect_language(None, explicit=args.language, file_name=file_name)
    if decision.language is None:
        print(f"[error] language unresolved: {decision.reason}", file=sys.stderr)
        return 2
    language = decision.language

    input_kind = "file" if args.input else "snippet"
    source = args.input if args.input else None

    if args.dump_candidates:
        unit = frontend.parse(code, language, with_position=True)
        ctx = TransformContext(
            unit, language, frontend,
            input_kind=input_kind, source=source,
        )
        names = resolve_transforms(args.transform)
        dump = {}
        for name in names:
            t = get_transform(name)
            cands = t.find_candidates(ctx)
            for c in cands:
                if c.source_location is not None:
                    apply_input_context(c.source_location, input_kind, source)
            dump[name] = [c.to_dict() for c in cands]
        print(json.dumps(dump, ensure_ascii=False, indent=2))
        return 0

    current = code
    for name in resolve_transforms(args.transform):
        res = apply_transform(
            frontend, current, language, get_transform(name),
            pick=args.pick, seed=args.seed,
            compiler_validate=args.compiler_validate,
            input_kind=input_kind, source=source,
        )
        print(
            f"[{name}] status={res.status} changed={res.changed} "
            f"error={res.error}",
            file=sys.stderr,
        )
        if res.status == "success":
            current = res.transformed_code

    if args.out:
        Path(args.out).write_text(current, encoding="utf-8")
        print(f"[file] wrote {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(current)
    return 0


# -- batch -----------------------------------------------------------------
def cmd_batch(args) -> int:
    frontend = make_frontend(args)
    names = resolve_transforms(args.transforms)
    out_records: list[dict] = []
    log = RunLog()
    n_in = n_out = n_skip = n_fail = 0
    # Run-level metadata: tab_size is constant for the whole run, so it is
    # recorded once here rather than on every SourceLocation. It tells consumers
    # how to interpret column numbers on tab-indented lines.
    log.add(event="run_meta", tab_size=frontend.tab_size,
            transforms=names, fields=args.fields, mode=args.mode)

    # Optional input selection (handy for previewing on stdout):
    #   --lines  process only these 1-based input line numbers
    #   --limit  process only the first N records
    line_filter: set[int] | None = None
    if args.lines:
        line_filter = {int(x) for x in args.lines.split(",") if x.strip()}

    for item in iter_jsonl(args.jsonl):
        if line_filter is not None and item.lineno not in line_filter:
            continue
        if args.limit is not None and n_in >= args.limit:
            break
        if item.error:
            log.add(lineno=item.lineno, status="error", error=item.error)
            n_fail += 1
            continue
        n_in += 1
        record = item.record
        fields = detect_code_fields(record, which=args.fields)
        if not fields:
            log.add(lineno=item.lineno, status="skipped", error="no_code_fields")
            n_skip += 1
            continue
        decision = detect_language(record, explicit=args.language)

        for field in fields:
            code = record[field]
            if decision.language is None:
                res_meta = {
                    "name": ",".join(names), "status": "skipped",
                    "target_field": field, "error": "language_unresolved",
                    "reason": decision.reason,
                }
                rec = dict(record)
                rec["transform"] = res_meta
                out_records.append(rec)
                log.add(lineno=item.lineno, field=field, status="skipped",
                        error="language_unresolved", reason=decision.reason)
                n_skip += 1
                continue
            language = decision.language

            if args.mode == "separate":
                for name in names:
                    res = apply_transform(
                        frontend, code, language, get_transform(name),
                        pick=args.pick, seed=args.seed, target_field=field,
                        compiler_validate=args.compiler_validate,
                        input_kind="jsonl_field", source=field,
                    )
                    out_records.append(build_output_record(record, field, res))
                    before = _first_before(res.selected_candidates)
                    log.add(lineno=item.lineno, field=field, transform=name,
                            status=res.status, changed=res.changed, error=res.error,
                            candidate_count=res.candidate_count,
                            before_line=before.get("start_line"),
                            relative_to=before.get("relative_to"))
                    n_out += 1
                    if res.status == "failed":
                        n_fail += 1
            else:  # combined
                current = code
                from .model.result import TransformResult
                combined = TransformResult(
                    name="+".join(names), family="combined",
                    seed=args.seed, target_field=field, language=language,
                    original_code=code, transformed_code=code,
                )
                statuses = []
                for name in names:
                    res = apply_transform(
                        frontend, current, language, get_transform(name),
                        pick=args.pick, seed=args.seed, target_field=field,
                        compiler_validate=args.compiler_validate,
                        input_kind="jsonl_field", source=field,
                    )
                    statuses.append((name, res.status))
                    # Keep the first transform that actually selected sites: its
                    # input is the original code, so its BEFORE positions stay in
                    # original coordinates.
                    if not combined.selected_candidates and res.selected_candidates:
                        combined.candidate_count = res.candidate_count
                        combined.selected_candidates = res.selected_candidates
                    if res.status == "success":
                        current = res.transformed_code
                combined.transformed_code = current
                combined.changed = current != code
                combined.status = "success" if combined.changed else "skipped"
                combined.validation = {"per_transform": dict(statuses)}
                combined.transformed_location = [
                    s.to_dict() for s in changed_line_spans(code, current, field)
                ]
                out_records.append(build_output_record(record, field, combined))
                log.add(lineno=item.lineno, field=field, transform=combined.name,
                        status=combined.status, changed=combined.changed)
                n_out += 1

    # --out '-' or 'stdout' streams the records to stdout for quick inspection
    # instead of writing a file (run_log is only written if --log is given).
    if args.out in ("-", "stdout"):
        indent = 2 if args.pretty else None
        for rec in out_records:
            sys.stdout.write(json.dumps(rec, ensure_ascii=False, indent=indent) + "\n")
        if args.log:
            log.write(args.log)
        print(
            f"[batch] in={n_in} out_records={n_out} skipped={n_skip} failed={n_fail} "
            f"-> stdout" + (f" (log: {args.log})" if args.log else ""),
            file=sys.stderr,
        )
        if args.report:
            generate_report(None, args.report, tab_size=frontend.tab_size,
                            records=out_records)
            print(f"[batch] report -> {args.report}", file=sys.stderr)
        return 0

    write_jsonl(args.out, out_records)
    log_path = args.log or str(Path(args.out).with_name("run_log.jsonl"))
    log.write(log_path)
    print(
        f"[batch] in={n_in} out_records={n_out} skipped={n_skip} failed={n_fail} "
        f"-> {args.out} (log: {log_path})",
        file=sys.stderr,
    )
    if args.report:
        generate_report(args.out, args.report, tab_size=frontend.tab_size)
        print(f"[batch] report -> {args.report}", file=sys.stderr)
    return 0


# -- report ----------------------------------------------------------------
def cmd_report(args) -> int:
    generate_report(args.input, args.out, max_samples=args.max_samples)
    print(f"[report] wrote {args.out}", file=sys.stderr)
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="cpp_transform")
    sub = ap.add_subparsers(dest="command", required=True)

    f = sub.add_parser("file", help="transform a single file/snippet")
    f.add_argument("--input", help="source file (default: stdin)")
    f.add_argument("--language", help="C or C++ (overrides detection)")
    f.add_argument("--transform", default="variable_chain",
                   help="transform name(s), comma-separated, or 'all'")
    f.add_argument("--pick", default="first")
    f.add_argument("--seed", type=int, default=42)
    f.add_argument("--out", help="output file (default: stdout)")
    f.add_argument("--dump-candidates", action="store_true")
    f.add_argument("--compiler-validate", action="store_true")
    add_frontend_args(f)
    f.set_defaults(func=cmd_file)

    b = sub.add_parser("batch", help="transform a JSONL dataset")
    b.add_argument("--jsonl", required=True)
    b.add_argument("--out", required=True,
                   help="output JSONL path, or '-'/'stdout' to print to stdout")
    b.add_argument("--pretty", action="store_true",
                   help="pretty-print JSON (indented); handy with --out -")
    b.add_argument("--limit", type=int, default=None,
                   help="process only the first N records (quick preview)")
    b.add_argument("--lines", default=None,
                   help="process only these 1-based input line numbers, e.g. '1,3,5'")
    b.add_argument("--transforms", default="all")
    b.add_argument("--fields", choices=["vuln", "fixed", "both"], default="vuln")
    b.add_argument("--mode", choices=["separate", "combined"], default="separate")
    b.add_argument("--pick", default="first")
    b.add_argument("--seed", type=int, default=42)
    b.add_argument("--language", help="force C/C++ for all records")
    b.add_argument("--report", help="also write a markdown report here")
    b.add_argument("--log", help="run log path (default: run_log.jsonl next to --out)")
    b.add_argument("--compiler-validate", action="store_true")
    add_frontend_args(b)
    b.set_defaults(func=cmd_batch)

    r = sub.add_parser("report", help="render a markdown report from output JSONL")
    r.add_argument("--input", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--max-samples", type=int, default=10)
    r.set_defaults(func=cmd_report)

    return ap


def main(argv: list[str] | None = None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

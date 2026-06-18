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

    if args.dump_candidates:
        unit = frontend.parse(code, language)
        ctx = TransformContext(unit, language, frontend)
        names = resolve_transforms(args.transform)
        dump = {}
        for name in names:
            t = get_transform(name)
            dump[name] = [c.to_dict() for c in t.find_candidates(ctx)]
        print(json.dumps(dump, ensure_ascii=False, indent=2))
        return 0

    current = code
    for name in resolve_transforms(args.transform):
        res = apply_transform(
            frontend, current, language, get_transform(name),
            pick=args.pick, seed=args.seed,
            compiler_validate=args.compiler_validate,
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

    for item in iter_jsonl(args.jsonl):
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
                    )
                    out_records.append(build_output_record(record, field, res))
                    log.add(lineno=item.lineno, field=field, transform=name,
                            status=res.status, changed=res.changed, error=res.error)
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
                    )
                    statuses.append((name, res.status))
                    if res.status == "success":
                        current = res.transformed_code
                combined.transformed_code = current
                combined.changed = current != code
                combined.status = "success" if combined.changed else "skipped"
                combined.validation = {"per_transform": dict(statuses)}
                out_records.append(build_output_record(record, field, combined))
                log.add(lineno=item.lineno, field=field, transform=combined.name,
                        status=combined.status, changed=combined.changed)
                n_out += 1

    write_jsonl(args.out, out_records)
    log_path = args.log or str(Path(args.out).with_name("run_log.jsonl"))
    log.write(log_path)
    print(
        f"[batch] in={n_in} out_records={n_out} skipped={n_skip} failed={n_fail} "
        f"-> {args.out} (log: {log_path})",
        file=sys.stderr,
    )
    if args.report:
        generate_report(args.out, args.report)
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
    b.add_argument("--out", required=True)
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

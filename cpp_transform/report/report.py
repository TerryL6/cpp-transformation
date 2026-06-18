"""Generate a Markdown report from transformed JSONL output.

Summarizes per-transform status counts, srcML reparse pass rate, and compiler
validation outcomes, then shows the first N before/after snippets with a unified
diff. Validation layers are reported separately and never conflated.
"""

from __future__ import annotations

import difflib
import json
from collections import Counter, defaultdict
from pathlib import Path


def _load(path: str | Path) -> list[dict]:
    records = []
    with Path(path).open("r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                records.append(json.loads(line))
    return records


def _diff(original: str, transformed: str, name: str) -> str:
    lines = difflib.unified_diff(
        original.splitlines(),
        transformed.splitlines(),
        fromfile=f"{name} (original)",
        tofile=f"{name} (transformed)",
        lineterm="",
    )
    return "\n".join(lines)


def generate_report(input_path: str | Path, output_path: str | Path, max_samples: int = 10) -> str:
    records = _load(input_path)
    status_by_transform: dict[str, Counter] = defaultdict(Counter)
    reparse = Counter()
    compiler = Counter()

    for rec in records:
        meta = rec.get("transform") or {}
        name = meta.get("name", "?")
        status_by_transform[name][meta.get("status", "?")] += 1
        val = meta.get("validation") or {}
        reparse[(val.get("srcml_reparse") or {}).get("status", "n/a")] += 1
        if "compiler" in val:
            compiler[val["compiler"].get("status", "n/a")] += 1

    lines: list[str] = ["# cpp_transform report", ""]
    lines.append(f"Total records: {len(records)}")
    lines.append("")
    lines.append("## Status by transform")
    lines.append("")
    for name in sorted(status_by_transform):
        counts = status_by_transform[name]
        summary = ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
        lines.append(f"- `{name}`: {summary}")
    lines.append("")
    lines.append("## srcML reparse")
    lines.append("")
    lines.append(", ".join(f"{k}={v}" for k, v in sorted(reparse.items())) or "n/a")
    lines.append("")
    if compiler:
        lines.append("## Compiler validation")
        lines.append("")
        lines.append(", ".join(f"{k}={v}" for k, v in sorted(compiler.items())))
        lines.append("")

    lines.append("## Samples")
    lines.append("")
    shown = 0
    for rec in records:
        if shown >= max_samples:
            break
        meta = rec.get("transform") or {}
        field = meta.get("target_field")
        if not field or field not in rec:
            continue
        original = rec.get(f"{field}_original", "")
        transformed = rec.get(field, "")
        name = meta.get("name", "?")
        header = f"### Sample {shown + 1}: `{name}` on `{field}` -> {meta.get('status')}"
        lines.append(header)
        if meta.get("error"):
            lines.append(f"_note: {meta['error']}_")
        diff = _diff(original, transformed, name)
        lines.append("")
        lines.append("```diff")
        lines.append(diff if diff.strip() else "(no change)")
        lines.append("```")
        lines.append("")
        shown += 1

    text = "\n".join(lines)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return text

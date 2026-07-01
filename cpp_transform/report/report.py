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


def generate_report(
    input_path: str | Path | None,
    output_path: str | Path,
    max_samples: int = 10,
    tab_size: int | None = None,
    records: list[dict] | None = None,
) -> str:
    records = records if records is not None else _load(input_path)
    status_by_transform: dict[str, Counter] = defaultdict(Counter)
    reparse = Counter()
    compiler = Counter()
    repo_val = Counter()
    anchor_status = Counter()
    anchor_records = 0
    loc_relative_to = Counter()
    loc_with_before = 0
    loc_with_after = 0

    for rec in records:
        meta = rec.get("transform") or {}
        name = meta.get("name", "?")
        status_by_transform[name][meta.get("status", "?")] += 1
        val = meta.get("validation") or {}
        reparse[(val.get("srcml_reparse") or {}).get("status", "n/a")] += 1
        if "compiler" in val:
            compiler[val["compiler"].get("status", "n/a")] += 1
        rv = meta.get("repo_validation")
        if rv:
            repo_val[rv.get("status", "n/a")] += 1
        va = meta.get("vuln_anchor")
        if va:
            anchor_records += 1
            for block in va:
                anchor_status[block.get("status", "n/a")] += 1
        selected = meta.get("selected_candidates") or []
        before = (selected[0].get("source_location") if selected else None) or {}
        if before:
            loc_with_before += 1
            loc_relative_to[before.get("relative_to", "n/a")] += 1
        if meta.get("transformed_location"):
            loc_with_after += 1

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

    if repo_val:
        lines.append("## Repository validation")
        lines.append("")
        lines.append(", ".join(f"{k}={v}" for k, v in sorted(repo_val.items())))
        lines.append("")

    if anchor_status:
        lines.append("## Vulnerability anchors")
        lines.append("")
        lines.append(f"Records with anchors: {anchor_records}/{len(records)}")
        lines.append("")
        lines.append(
            "- anchor status: "
            + ", ".join(f"{k}={v}" for k, v in sorted(anchor_status.items()))
        )
        lines.append("")

    lines.append("## Source locations")
    lines.append("")
    if tab_size is not None:
        lines.append(f"tab_size (run-level): {tab_size}")
        lines.append("")
    lines.append(
        f"Records with a captured before-location: {loc_with_before}/{len(records)}; "
        f"with an after-location: {loc_with_after}/{len(records)}"
    )
    lines.append("")
    lines.append(
        "- relative_to (before): "
        + (", ".join(f"{k}={v}" for k, v in sorted(loc_relative_to.items())) or "n/a")
    )
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

"""End-to-end batch: error isolation, language handling, output schema."""

from __future__ import annotations

import json

from cpp_transform.cli import main


def _read_jsonl(path):
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def test_batch_isolates_errors_and_marks_language(frontend, tmp_path):
    data = tmp_path / "in.jsonl"
    lines = [
        json.dumps({"file_name": "ok.c", "func_vuln": "int f(int a){ int x = a; return x; }"}),
        "this is not json",
        json.dumps({"func_vuln": "int g(int a){ int y = a; return y; }"}),  # no language
    ]
    data.write_text("\n".join(lines) + "\n", encoding="utf-8")
    out = tmp_path / "out.jsonl"

    rc = main([
        "batch", "--jsonl", str(data), "--out", str(out),
        "--transforms", "variable_chain", "--fields", "vuln",
        "--mode", "separate",
    ])
    assert rc == 0
    records = _read_jsonl(out)
    # one transformed record for the good line + one skipped record for the
    # language-unresolved line.
    statuses = [r["transform"]["status"] for r in records]
    assert "success" in statuses
    assert "skipped" in statuses

    # the good record preserves the original under <field>_original
    good = [r for r in records if r["transform"]["status"] == "success"][0]
    assert "func_vuln_original" in good
    assert "__chain_" in good["func_vuln"]

    log = _read_jsonl(out.parent / "run_log.jsonl")
    assert any(e.get("status") == "error" for e in log)  # bad json line
    assert any(e.get("error") == "language_unresolved" for e in log)


def test_batch_combined_mode(frontend, tmp_path):
    data = tmp_path / "in.jsonl"
    data.write_text(
        json.dumps({
            "file_name": "ok.c",
            "func_vuln": "#include <stdlib.h>\nvoid h(int a){ int x = a; free((void*)0); }",
        }) + "\n",
        encoding="utf-8",
    )
    out = tmp_path / "out.jsonl"
    rc = main([
        "batch", "--jsonl", str(data), "--out", str(out),
        "--transforms", "all", "--fields", "vuln", "--mode", "combined",
    ])
    assert rc == 0
    records = _read_jsonl(out)
    assert len(records) == 1
    assert records[0]["transform"]["family"] == "combined"

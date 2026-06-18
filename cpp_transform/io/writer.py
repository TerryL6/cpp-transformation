"""Output writing: transformed JSONL records (+ original preservation) and logs."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Iterable

from ..model.result import TransformResult


def build_output_record(
    record: dict, target_field: str, result: TransformResult
) -> dict:
    """Preserve the original record; replace the target field with transformed
    code and stash the original under ``<field>_original`` plus a metadata block.
    """
    out = copy.deepcopy(record)
    out[f"{target_field}_original"] = result.original_code
    out[target_field] = result.transformed_code
    out["transform"] = result.to_dict()
    return out


def write_jsonl(path: str | Path, records: Iterable[dict]) -> int:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with p.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n += 1
    return n


class RunLog:
    """Accumulates one structured line per (record x field x transform) attempt."""

    def __init__(self) -> None:
        self.entries: list[dict] = []

    def add(self, **fields) -> None:
        self.entries.append(fields)

    def write(self, path: str | Path) -> int:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8") as fh:
            for e in self.entries:
                fh.write(json.dumps(e, ensure_ascii=False) + "\n")
        return len(self.entries)

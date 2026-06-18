"""Dataset layer: streaming JSONL reader, field detection, language detection.

Language detection never silently defaults: priority is explicit override >
dataset language field > file extension. If none resolve, the record is marked
so the pipeline can record skipped/error (and the batch continues).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

# code field name aliases
VULN_FIELDS = ("func_vuln", "vuln_func")
FIXED_FIELDS = ("func_fixed", "fixed_func")
LANGUAGE_FIELDS = ("language", "lang")

_EXT_LANG = {
    ".c": "C",
    ".cpp": "C++", ".cc": "C++", ".cxx": "C++", ".c++": "C++",
    ".hpp": "C++", ".hh": "C++", ".hxx": "C++",
    # NOTE: .h is ambiguous (C vs C++); intentionally not mapped.
}

_NORMALIZE = {
    "c": "C",
    "c++": "C++", "cpp": "C++", "cxx": "C++", "cplusplus": "C++",
}


@dataclass
class LanguageDecision:
    language: str | None
    source: str  # "explicit" | "field" | "extension" | "unresolved"
    reason: str = ""


def normalize_language(value: str | None) -> str | None:
    if not value:
        return None
    return _NORMALIZE.get(value.strip().lower())


def detect_language(
    record: dict | None,
    explicit: str | None = None,
    file_name: str | None = None,
) -> LanguageDecision:
    norm = normalize_language(explicit)
    if norm:
        return LanguageDecision(norm, "explicit")
    if record:
        for f in LANGUAGE_FIELDS:
            norm = normalize_language(record.get(f))
            if norm:
                return LanguageDecision(norm, "field", f"from record field {f!r}")
        if file_name is None:
            file_name = record.get("file_name") or record.get("filename")
    if file_name:
        ext = Path(file_name).suffix.lower()
        if ext in _EXT_LANG:
            return LanguageDecision(_EXT_LANG[ext], "extension", f"ext {ext}")
        if ext == ".h":
            return LanguageDecision(
                None, "unresolved", ".h is ambiguous; pass --language"
            )
    return LanguageDecision(
        None, "unresolved", "no --language, language field, or known extension"
    )


def detect_code_fields(record: dict, which: str = "vuln") -> list[str]:
    """Return present code field names for the requested set."""
    present: list[str] = []
    groups: list[tuple[str, ...]] = []
    if which in ("vuln", "both"):
        groups.append(VULN_FIELDS)
    if which in ("fixed", "both"):
        groups.append(FIXED_FIELDS)
    for group in groups:
        for f in group:
            if isinstance(record.get(f), str) and record.get(f).strip():
                present.append(f)
                break  # first alias wins per group
    return present


@dataclass
class JsonlItem:
    lineno: int
    record: dict | None
    error: str | None = None


def iter_jsonl(path: str | Path) -> Iterator[JsonlItem]:
    """Stream JSONL. Malformed lines yield an error item instead of crashing."""
    p = Path(path)
    with p.open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as exc:
                yield JsonlItem(lineno, None, error=f"json decode error: {exc}")
                continue
            yield JsonlItem(lineno, rec)

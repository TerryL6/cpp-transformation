"""Place a transformed function back into its real source file.

Whole-function replacement only: we locate the *original* function text as a
unique block of lines in the target file and swap it for the transformed text.
Matching is line-based with two passes - exact, then trailing-whitespace
insensitive - and we only ever edit on a **unique** match. Zero or multiple
matches yield ``skipped_ambiguous``: per the V3 rule we never guess or patch the
wrong location.

This is plain text line replacement on a concrete file (not the strict srcML
tree-to-tree path, which governs how the *transformed function itself* was
produced); here we are only splicing an already-generated function back into the
repository file before building.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class PlacementResult:
    status: str                       # placed | skipped_ambiguous | error
    mapping_status: str | None = None  # exact | exact_normalized | not_found | multiple
    file_path: str | None = None
    start_line: int | None = None     # 1-based, inclusive
    end_line: int | None = None       # 1-based, inclusive
    detail: str | None = None

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "mapping_status": self.mapping_status,
            "file_path": self.file_path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "detail": self.detail,
        }


def _find_spans(
    file_lines: list[str], orig_lines: list[str], normalize
) -> list[int]:
    """Return all start indices where ``orig_lines`` matches a window of
    ``file_lines`` under ``normalize`` (a per-line transform)."""
    n, m = len(file_lines), len(orig_lines)
    if m == 0 or m > n:
        return []
    norm_file = [normalize(l) for l in file_lines]
    norm_orig = [normalize(l) for l in orig_lines]
    first = norm_orig[0]
    hits: list[int] = []
    for i in range(n - m + 1):
        if norm_file[i] != first:
            continue
        if norm_file[i:i + m] == norm_orig:
            hits.append(i)
    return hits


def _strip_eol(s: str) -> str:
    return s.rstrip("\n").rstrip("\r")


def locate_function(
    file_text: str, original_text: str
) -> tuple[str, list[int], int]:
    """Locate ``original_text`` in ``file_text`` by lines.

    Returns ``(mapping_status, start_indices, block_len)`` where indices are
    0-based line offsets. ``mapping_status`` is ``exact`` / ``exact_normalized``
    / ``multiple`` / ``not_found``.
    """
    file_lines = file_text.splitlines()
    orig_lines = original_text.splitlines()
    block_len = len(orig_lines)

    # Pass 1: exact (ignore only the line-ending itself).
    hits = _find_spans(file_lines, orig_lines, _strip_eol)
    if len(hits) == 1:
        return "exact", hits, block_len
    if len(hits) > 1:
        return "multiple", hits, block_len

    # Pass 2: trailing-whitespace insensitive.
    hits = _find_spans(file_lines, orig_lines, lambda l: _strip_eol(l).rstrip())
    if len(hits) == 1:
        return "exact_normalized", hits, block_len
    if len(hits) > 1:
        return "multiple", hits, block_len

    return "not_found", [], block_len


def place_function(
    file_path: str | Path,
    original_text: str,
    transformed_text: str,
) -> PlacementResult:
    """Replace the unique occurrence of ``original_text`` in ``file_path``."""
    path = Path(file_path)
    try:
        file_text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return PlacementResult("error", detail=f"read_failed: {exc}",
                               file_path=str(path))

    mapping_status, hits, block_len = locate_function(file_text, original_text)
    if mapping_status in ("not_found", "multiple"):
        return PlacementResult(
            "skipped_ambiguous", mapping_status=mapping_status,
            file_path=str(path),
            detail=f"{len(hits)} match(es)",
        )

    start = hits[0]
    end = start + block_len  # exclusive

    # Preserve the file's dominant newline; default to "\n".
    newline = "\r\n" if "\r\n" in file_text else "\n"
    file_lines = file_text.splitlines(keepends=True)
    had_trailing_nl = file_lines[end - 1].endswith("\n") if file_lines else True

    repl_lines = [ln + newline for ln in transformed_text.splitlines()]
    if repl_lines and not had_trailing_nl:
        repl_lines[-1] = repl_lines[-1].rstrip("\r\n")

    new_lines = file_lines[:start] + repl_lines + file_lines[end:]
    try:
        path.write_text("".join(new_lines), encoding="utf-8")
    except OSError as exc:
        return PlacementResult("error", detail=f"write_failed: {exc}",
                               file_path=str(path))

    return PlacementResult(
        "placed", mapping_status=mapping_status, file_path=str(path),
        start_line=start + 1, end_line=end,  # 1-based inclusive
    )

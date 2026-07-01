"""Result models recording exactly what happened to one transform attempt."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TransformResult:
    name: str
    family: str
    status: str = "skipped"  # success | skipped | failed
    seed: int | None = None
    target_field: str | None = None
    language: str | None = None
    changed: bool = False
    original_code: str = ""
    transformed_code: str = ""
    # Source-location tracking (V2):
    #   candidate_count       - total candidates located (selected + not)
    #   selected_candidates   - slim dicts of the candidates actually changed,
    #                           each carrying its BEFORE source_location
    #   transformed_location  - AFTER: list of changed line ranges (diff hunks,
    #                           output coordinates, line-level only)
    candidate_count: int = 0
    selected_candidates: list[dict[str, Any]] = field(default_factory=list)
    transformed_location: list[dict[str, Any]] = field(default_factory=list)
    validation: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    # Repository-level validation (V3). Stored ALONGSIDE the lightweight
    # ``validation`` block (success|skipped|failed), never overwriting it. Left
    # as ``None`` when repo validation was not attempted.
    repo_validation: dict[str, Any] | None = None
    # Vulnerability anchoring (V4). A list of per-anchor blocks
    # ``{id, role, before, after, status}`` recording whether each anchored vuln
    # node survived the transform and where it landed. Stored ALONGSIDE
    # ``validation`` / ``repo_validation``, never overwriting them. Left as
    # ``None`` when anchor tracking was not requested (``--track-anchor`` off).
    vuln_anchor: list[dict[str, Any]] | None = None

    def to_dict(self) -> dict[str, Any]:
        out = {
            "name": self.name,
            "family": self.family,
            "status": self.status,
            "seed": self.seed,
            "target_field": self.target_field,
            "language": self.language,
            "changed": self.changed,
            "candidate_count": self.candidate_count,
            "selected_candidates": self.selected_candidates,
            "transformed_location": self.transformed_location,
            "validation": self.validation,
            "error": self.error,
        }
        if self.repo_validation is not None:
            out["repo_validation"] = self.repo_validation
        if self.vuln_anchor is not None:
            out["vuln_anchor"] = self.vuln_anchor
        return out

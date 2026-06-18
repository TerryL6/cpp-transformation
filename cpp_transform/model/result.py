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
    candidate: dict[str, Any] | None = None
    validation: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "family": self.family,
            "status": self.status,
            "seed": self.seed,
            "target_field": self.target_field,
            "language": self.language,
            "changed": self.changed,
            "candidate": self.candidate,
            "validation": self.validation,
            "error": self.error,
        }

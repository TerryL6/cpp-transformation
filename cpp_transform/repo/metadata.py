"""Repository metadata parsing and revision resolution.

A dataset record points at a real repository via ``project_url`` /
``commit_id`` / ``file_name`` / ``func_name``. This module turns that into a
:class:`RepoMetadata` value object and, crucially, derives **which revision to
check out**.

``commit_id`` semantics (SVEN convention, empirically confirmed): ``commit_id``
is the **fix commit**.

* ``func_fixed`` is the function as it exists *at* ``commit_id``.
* ``func_vuln`` is the function at the **parent** ``commit_id^1`` (the vulnerable
  state).

So to validate ``func_vuln`` we must check out ``commit_id^1`` - only there does
the target file naturally contain ``func_vuln`` for exact-text placement, and
only there is the baseline build "vulnerable state, unmodified". To validate
``func_fixed`` we check out ``commit_id`` itself.

This layer is **dataset-agnostic**: it does not assume every record carries every
field. Missing required fields make the metadata *insufficient*, which the
pipeline maps to ``skipped_no_repo`` (never a transform failure).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ..io.dataset import FIXED_FIELDS, VULN_FIELDS

# Which revision a code field's transformation must be validated against,
# relative to the fix commit ``commit_id``.
REL_PARENT = "parent"   # func_vuln -> commit_id^1 (vulnerable state)
REL_FIX = "fix"         # func_fixed -> commit_id  (fixed state)
REL_UNKNOWN = "unknown"  # field not classifiable as vuln/fixed

# Fields required before a repository-level build can even be attempted.
REQUIRED_FIELDS = ("project_url", "commit_id", "file_name", "func_name")


@dataclass
class RepoMetadata:
    """Repository context for one (record x code-field) validation attempt."""

    project: str | None = None
    project_url: str | None = None
    commit_id: str | None = None          # the fix commit, as given in the record
    file_name: str | None = None
    func_name: str | None = None
    vul_type: str | None = None
    target_field: str | None = None       # e.g. "func_vuln" / "func_fixed"

    # Derived revision resolution:
    revision_relation: str = REL_UNKNOWN  # parent | fix | unknown
    checkout_revision: str | None = None  # git rev-expression to check out

    def to_dict(self) -> dict[str, Any]:
        return {
            "project": self.project,
            "project_url": self.project_url,
            "commit_id": self.commit_id,
            "file_name": self.file_name,
            "func_name": self.func_name,
            "vul_type": self.vul_type,
            "target_field": self.target_field,
            "revision_relation": self.revision_relation,
            "checkout_revision": self.checkout_revision,
        }


@dataclass
class MetadataDecision:
    """Outcome of parsing repo metadata from a record.

    ``sufficient`` is ``True`` only when all :data:`REQUIRED_FIELDS` are present
    (and, for code fields, the checkout revision could be derived). When it is
    ``False``, ``missing`` lists the reasons and the pipeline records
    ``skipped_no_repo``.
    """

    metadata: RepoMetadata
    sufficient: bool
    missing: list[str] = field(default_factory=list)

    @property
    def reason(self) -> str:
        return "ok" if self.sufficient else "missing:" + ",".join(self.missing)


def classify_field(target_field: str | None) -> str:
    """Map a code-field name to the revision it must be validated against."""
    if target_field is None:
        return REL_UNKNOWN
    if target_field in VULN_FIELDS:
        return REL_PARENT
    if target_field in FIXED_FIELDS:
        return REL_FIX
    return REL_UNKNOWN


def resolve_checkout_revision(commit_id: str | None, relation: str) -> str | None:
    """Derive the git rev-expression to check out from the fix commit.

    * ``parent`` (func_vuln)  -> ``<commit_id>^1`` (first parent / vulnerable)
    * ``fix``    (func_fixed) -> ``<commit_id>``   (the fix commit itself)
    * ``unknown``             -> ``None`` (cannot decide safely)
    """
    if not commit_id:
        return None
    if relation == REL_PARENT:
        return f"{commit_id}^1"
    if relation == REL_FIX:
        return commit_id
    return None


def _clean(value: Any) -> str | None:
    """Return a stripped non-empty string, or ``None``."""
    if isinstance(value, str):
        v = value.strip()
        return v or None
    return None


def parse_repo_metadata(
    record: dict,
    target_field: str | None = None,
) -> MetadataDecision:
    """Parse repository metadata from a dataset record for one code field.

    Does not touch the network or filesystem; it only reads fields and derives
    the checkout revision. Sufficiency is reported, never raised.
    """
    meta = RepoMetadata(
        project=_clean(record.get("project")),
        project_url=_clean(record.get("project_url")),
        commit_id=_clean(record.get("commit_id")),
        file_name=_clean(record.get("file_name")) or _clean(record.get("filename")),
        func_name=_clean(record.get("func_name")),
        vul_type=_clean(record.get("vul_type")),
        target_field=target_field,
    )
    meta.revision_relation = classify_field(target_field)
    meta.checkout_revision = resolve_checkout_revision(
        meta.commit_id, meta.revision_relation
    )

    missing: list[str] = []
    for f in REQUIRED_FIELDS:
        if getattr(meta, f) is None:
            missing.append(f)
    # Even with a commit_id, an unclassifiable field means we cannot know whether
    # to check out the parent or the fix commit -> not safe to attempt.
    if meta.commit_id is not None and meta.checkout_revision is None:
        missing.append("revision_relation")

    return MetadataDecision(metadata=meta, sufficient=not missing, missing=missing)


def repo_cache_key(project_url: str | None) -> str | None:
    """A filesystem-safe cache slug derived from a clone URL.

    ``https://github.com/kkos/oniguruma`` -> ``github.com_kkos_oniguruma``.
    Returns ``None`` when no URL is available.
    """
    if not project_url:
        return None
    s = re.sub(r"^[a-zA-Z]+://", "", project_url.strip())
    s = s.rstrip("/")
    if s.endswith(".git"):
        s = s[:-4]
    return re.sub(r"[^A-Za-z0-9._-]+", "_", s)

"""Map per-stage outcomes to the ``repo_validation`` status enum.

Pure decision logic, so it is trivially testable. The orchestration (actually
running provision/build/placement) lives elsewhere; this only adjudicates.

Status enum (mirrors the plan):
``passed | failed | baseline_failed | skipped_no_repo | skipped_ambiguous |
environment_error | timeout | not_attempted``.

Precedence reflects the workflow: metadata -> provision -> baseline build ->
placement -> transformed build. The pivotal distinction is **baseline vs
transformed**: if the unmodified repo already fails, it is ``baseline_failed``
(not our fault); only a transformed-build failure on top of a passing baseline is
a real ``failed`` regression.
"""

from __future__ import annotations

from .build import BuildResult
from .placement import PlacementResult

# Provision error codes that mean "infrastructure/network/toolchain problem".
_PROVISION_ENV = {
    "clone_failed", "worktree_failed", "revision_not_found", "bad_url",
    "no_project_url", "git",
}
# Provision error codes that mean "this record cannot be validated safely".
_PROVISION_SKIP = {
    "merge_commit", "no_parent", "unknown_relation", "no_commit_id",
}


def _code(error: str | None) -> str:
    """Reason code = text before the first ':' (details are appended after)."""
    if not error:
        return ""
    return error.split(":", 1)[0].strip()


def classify(
    *,
    metadata_sufficient: bool,
    provision_error: str | None = None,
    baseline: BuildResult | None = None,
    placement: PlacementResult | None = None,
    transformed: BuildResult | None = None,
) -> dict:
    """Adjudicate one repo-validation attempt into a status dict."""
    out: dict = {
        "status": "not_attempted",
        "baseline_status": baseline.status if baseline else None,
        "mapping_status": placement.mapping_status if placement else None,
        "detail": None,
    }

    if not metadata_sufficient:
        out["status"] = "skipped_no_repo"
        return out

    if provision_error is not None:
        code = _code(provision_error)
        if code in _PROVISION_SKIP:
            out["status"] = "skipped_no_repo"
        else:
            out["status"] = "environment_error"
        out["detail"] = provision_error
        return out

    # -- baseline build -----------------------------------------------------
    if baseline is None:
        out["status"] = "not_attempted"
        return out
    if baseline.status == "timeout":
        out["status"] = "timeout"
        out["detail"] = "baseline_timeout"
        return out
    if baseline.status in ("failed", "error"):
        out["status"] = "baseline_failed"
        out["detail"] = f"baseline_{baseline.status}"
        return out

    # -- placement ----------------------------------------------------------
    if placement is None:
        out["status"] = "not_attempted"
        return out
    if placement.status == "skipped_ambiguous":
        out["status"] = "skipped_ambiguous"
        out["detail"] = placement.mapping_status
        return out
    if placement.status == "error":
        out["status"] = "environment_error"
        out["detail"] = placement.detail
        return out

    # -- transformed build --------------------------------------------------
    if transformed is None:
        out["status"] = "not_attempted"
        return out
    if transformed.status == "timeout":
        out["status"] = "timeout"
        out["detail"] = "transformed_timeout"
    elif transformed.status == "passed":
        out["status"] = "passed"
    elif transformed.status == "failed":
        out["status"] = "failed"  # regression: baseline passed, transformed broke
        out["detail"] = f"transformed_stage={transformed.failed_stage}"
    else:  # error launching transformed build though baseline ran
        out["status"] = "environment_error"
        out["detail"] = f"transformed_{transformed.status}"
    return out

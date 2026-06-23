"""Status classification tests (pure decision logic)."""

from __future__ import annotations

from cpp_transform.repo.build import BuildResult
from cpp_transform.repo.classify import classify
from cpp_transform.repo.placement import PlacementResult


def _b(status, **kw):
    return BuildResult(status=status, **kw)


def _p(status="placed", mapping_status="exact"):
    return PlacementResult(status=status, mapping_status=mapping_status)


def test_insufficient_metadata():
    assert classify(metadata_sufficient=False)["status"] == "skipped_no_repo"


def test_provision_env_error():
    r = classify(metadata_sufficient=True, provision_error="clone_failed: net")
    assert r["status"] == "environment_error"


def test_provision_merge_commit_is_skip():
    r = classify(metadata_sufficient=True, provision_error="merge_commit")
    assert r["status"] == "skipped_no_repo"


def test_baseline_failed_is_not_a_regression():
    r = classify(metadata_sufficient=True, baseline=_b("failed", returncode=2))
    assert r["status"] == "baseline_failed"


def test_baseline_timeout():
    r = classify(metadata_sufficient=True, baseline=_b("timeout"))
    assert r["status"] == "timeout"


def test_placement_ambiguous_short_circuits():
    r = classify(
        metadata_sufficient=True,
        baseline=_b("passed"),
        placement=_p("skipped_ambiguous", "multiple"),
    )
    assert r["status"] == "skipped_ambiguous" and r["mapping_status"] == "multiple"


def test_passed_end_to_end():
    r = classify(
        metadata_sufficient=True,
        baseline=_b("passed"),
        placement=_p(),
        transformed=_b("passed"),
    )
    assert r["status"] == "passed" and r["baseline_status"] == "passed"


def test_regression_failed():
    r = classify(
        metadata_sufficient=True,
        baseline=_b("passed"),
        placement=_p(),
        transformed=_b("failed", returncode=1, failed_stage="build[0]"),
    )
    assert r["status"] == "failed"


def test_transformed_timeout():
    r = classify(
        metadata_sufficient=True,
        baseline=_b("passed"),
        placement=_p(),
        transformed=_b("timeout"),
    )
    assert r["status"] == "timeout"


def test_not_attempted_when_stage_missing():
    # baseline passed but nothing else attempted yet
    r = classify(metadata_sufficient=True, baseline=_b("passed"))
    assert r["status"] == "not_attempted"

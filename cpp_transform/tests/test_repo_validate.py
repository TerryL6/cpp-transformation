"""Orchestrator tests for repository-level validation.

The end-to-end happy path uses a local git repo with a trivial ``Makefile`` (so
no real toolchain/autotools is needed) - it proves the wiring: provision parent
-> baseline build -> placement -> transformed build -> classify -> log + cleanup.
"""

from __future__ import annotations

import os
import shutil
import subprocess

import pytest

from cpp_transform.repo.validate import RepoValidateConfig, validate_record

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None or shutil.which("make") is None,
    reason="git/make unavailable",
)

_ENV = {
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
}

_FUNC = "int foo(int a)\n{\n  return a;\n}"
_FUNC_NEW = "int foo(int a)\n{\n  int __c = a;\n  return __c;\n}"
_FILE = "#include <stdio.h>\n\n" + _FUNC + "\n"
_MAKEFILE = "all:\n\ttrue\n"  # builds without a compiler


def _git(args, cwd):
    env = {**os.environ, **_ENV}
    return subprocess.run(
        ["git", *args], cwd=str(cwd), env=env, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
    )


def _make_repo(path):
    path.mkdir(parents=True, exist_ok=True)
    _git(["init", "-q", "-b", "main"], path)
    (path / "f.c").write_text(_FILE, encoding="utf-8")
    (path / "Makefile").write_text(_MAKEFILE, encoding="utf-8")
    _git(["add", "."], path)
    _git(["commit", "-q", "-m", "vuln"], path)  # parent (vulnerable state)
    (path / "NOTES").write_text("fix\n", encoding="utf-8")
    _git(["add", "."], path)
    _git(["commit", "-q", "-m", "fix"], path)   # the fix commit (commit_id)
    return _git(["rev-parse", "HEAD"], path).stdout.strip()


def test_insufficient_metadata_skips():
    out = validate_record({"project": "x"}, "func_vuln", _FUNC, _FUNC_NEW)
    assert out["status"] == "skipped_no_repo"


def test_end_to_end_passed(tmp_path):
    src = tmp_path / "src"
    fix_sha = _make_repo(src)
    record = {
        "project": "toy",
        "project_url": str(src),
        "commit_id": fix_sha,
        "file_name": "f.c",
        "func_name": "foo",
    }
    config = RepoValidateConfig(
        cache_root=tmp_path / "cache", log_dir=tmp_path / "logs"
    )
    out = validate_record(record, "func_vuln", _FUNC, _FUNC_NEW, config)

    assert out["status"] == "passed", out
    assert out["baseline_status"] == "passed"
    assert out["mapping_status"] == "exact"
    assert out["matched_span"]["file"] == "f.c"
    assert out["recipe"] == "make"
    # a build log was written
    assert out["build_log_ref"] and os.path.exists(out["build_log_ref"])


def test_ambiguous_when_func_text_absent(tmp_path):
    src = tmp_path / "src"
    fix_sha = _make_repo(src)
    record = {
        "project": "toy", "project_url": str(src), "commit_id": fix_sha,
        "file_name": "f.c", "func_name": "foo",
    }
    config = RepoValidateConfig(cache_root=tmp_path / "cache")
    # original_code that does not occur in the file -> cannot place
    out = validate_record(record, "func_vuln", "int bar(void){return 0;}",
                          _FUNC_NEW, config)
    assert out["status"] == "skipped_ambiguous"

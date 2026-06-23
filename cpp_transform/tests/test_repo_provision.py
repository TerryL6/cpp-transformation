"""Provisioning tests: cache clone, revision resolution, isolated worktree.

Fully offline - a tiny local git repo stands in for ``project_url`` (git clone
works from a local path), so nothing hits the network. Skipped when git is
unavailable.
"""

from __future__ import annotations

import shutil
import subprocess

import pytest

from cpp_transform.repo.metadata import REL_FIX, REL_PARENT, RepoMetadata
from cpp_transform.repo.provision import (
    cleanup,
    create_workspace,
    ensure_clone,
    provision,
    resolve_commit_sha,
)

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None, reason="git unavailable"
)

_ENV = {
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
}


def _git(args, cwd, **kw):
    import os
    env = {**os.environ, **_ENV}
    return subprocess.run(
        ["git", *args], cwd=str(cwd), env=env, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, **kw
    )


def _head(cwd) -> str:
    return _git(["rev-parse", "HEAD"], cwd).stdout.strip()


def _make_linear_repo(path):
    """parent commit (VULN) -> fix commit (FIXED). Returns (parent, fix) SHAs."""
    path.mkdir(parents=True, exist_ok=True)
    _git(["init", "-q", "-b", "main"], path)
    (path / "f.c").write_text("VULN\n", encoding="utf-8")
    _git(["add", "."], path)
    _git(["commit", "-q", "-m", "vuln"], path)
    parent = _head(path)
    (path / "f.c").write_text("FIXED\n", encoding="utf-8")
    _git(["add", "."], path)
    _git(["commit", "-q", "-m", "fix"], path)
    fix = _head(path)
    return parent, fix


def _meta(url, commit_id, relation):
    m = RepoMetadata(project_url=str(url), commit_id=commit_id)
    m.revision_relation = relation
    return m


def test_resolve_parent_and_fix(tmp_path):
    repo = tmp_path / "repo"
    parent, fix = _make_linear_repo(repo)

    sha, err = resolve_commit_sha(repo, _meta(repo, fix, REL_FIX))
    assert err is None and sha == fix

    sha, err = resolve_commit_sha(repo, _meta(repo, fix, REL_PARENT))
    assert err is None and sha == parent


def test_resolve_root_commit_has_no_parent(tmp_path):
    repo = tmp_path / "repo"
    parent, _fix = _make_linear_repo(repo)
    # parent is the root commit; asking for ITS parent must fail cleanly.
    sha, err = resolve_commit_sha(repo, _meta(repo, parent, REL_PARENT))
    assert sha is None and err == "no_parent"


def test_resolve_merge_commit_is_refused(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(["init", "-q", "-b", "main"], repo)
    (repo / "f.c").write_text("base\n", encoding="utf-8")
    _git(["add", "."], repo)
    _git(["commit", "-q", "-m", "base"], repo)
    _git(["checkout", "-q", "-b", "feat"], repo)
    (repo / "g.c").write_text("feat\n", encoding="utf-8")
    _git(["add", "."], repo)
    _git(["commit", "-q", "-m", "feat"], repo)
    _git(["checkout", "-q", "main"], repo)
    (repo / "h.c").write_text("main\n", encoding="utf-8")
    _git(["add", "."], repo)
    _git(["commit", "-q", "-m", "main2"], repo)
    _git(["merge", "-q", "--no-ff", "-m", "merge", "feat"], repo)
    merge_sha = _head(repo)

    sha, err = resolve_commit_sha(repo, _meta(repo, merge_sha, REL_PARENT))
    assert sha is None and err == "merge_commit"


def test_revision_not_found(tmp_path):
    repo = tmp_path / "repo"
    _make_linear_repo(repo)
    sha, err = resolve_commit_sha(repo, _meta(repo, "deadbeef" * 5, REL_FIX))
    assert sha is None and err.startswith("revision_not_found")


def test_ensure_clone_caches_and_reuses(tmp_path):
    src = tmp_path / "src"
    _make_linear_repo(src)
    cache = tmp_path / "cache"
    p1, err = ensure_clone(str(src), cache_root=cache)
    assert err is None and (p1 / ".git").is_dir()
    p2, err2 = ensure_clone(str(src), cache_root=cache)
    assert err2 is None and p2 == p1  # reused, not re-cloned


def test_provision_checks_out_parent_content(tmp_path):
    src = tmp_path / "src"
    parent, fix = _make_linear_repo(src)
    cache = tmp_path / "cache"

    res = provision(_meta(src, fix, REL_PARENT), cache_root=cache)
    try:
        assert res.status == "ok", res.error
        assert res.commit_sha == parent
        # func_vuln validation must see the vulnerable (parent) content.
        assert (res.workspace.root / "f.c").read_text(encoding="utf-8") == "VULN\n"
    finally:
        cleanup(res.workspace)
    assert not res.workspace.root.exists()


def test_provision_checks_out_fix_content(tmp_path):
    src = tmp_path / "src"
    _parent, fix = _make_linear_repo(src)
    cache = tmp_path / "cache"

    res = provision(_meta(src, fix, REL_FIX), cache_root=cache)
    try:
        assert res.status == "ok", res.error
        assert (res.workspace.root / "f.c").read_text(encoding="utf-8") == "FIXED\n"
    finally:
        cleanup(res.workspace)


def test_provision_bad_url_errors(tmp_path):
    res = provision(_meta("", "abc", REL_FIX), cache_root=tmp_path / "cache")
    assert res.status == "error" and res.error == "no_project_url"

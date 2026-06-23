"""Repository provisioning: cache clone, revision resolution, isolated workspace.

Lifecycle for one validation attempt:

1. **Cache clone** - clone ``project_url`` once into a local cache directory
   (full history, so ``commit_id^1`` resolves); reuse it on later runs.
2. **Resolve revision** - turn the metadata's target revision into a concrete
   SHA, honoring the ``commit_id`` semantics: for ``func_vuln`` we take the
   parent (``commit_id^1``); root commits (no parent) and merge commits
   (multiple parents) are refused rather than guessed.
3. **Isolated workspace** - ``git worktree add --detach`` a throwaway working
   tree checked out at that SHA, so the cached clone is never mutated.
4. **Cleanup** - remove the worktree and its temp parent.

Everything returns structured results (``ProvisionResult``) instead of raising,
so the pipeline can record ``environment_error`` / ``skipped`` and keep the batch
going. ``git`` is invoked without a shell; no byte-offset or path tricks.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .metadata import REL_FIX, REL_PARENT, RepoMetadata, repo_cache_key

# Default location for cached clones; overridable by the caller / CLI.
DEFAULT_CACHE_ROOT = Path.home() / ".cache" / "cpp_transform" / "repos"

# Generous default for a one-time full clone (seconds).
CLONE_TIMEOUT_DEFAULT = 1800


@dataclass
class Workspace:
    """An isolated git worktree checked out at a concrete commit."""

    root: Path          # the working-tree path (where the source lives)
    commit_sha: str     # the concrete SHA checked out
    cache_dir: Path     # the backing cached clone
    _temp_parent: Path  # temp dir holding the worktree (removed on cleanup)


@dataclass
class ProvisionResult:
    """Outcome of provisioning. ``status`` is ``ok`` or ``error``."""

    status: str                       # "ok" | "error"
    workspace: Workspace | None = None
    error: str | None = None          # reason code (see module docstring)
    detail: str | None = None         # human-readable extra context
    commit_sha: str | None = None     # resolved SHA when known

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "error": self.error,
            "detail": self.detail,
            "commit_sha": self.commit_sha,
            "workspace": str(self.workspace.root) if self.workspace else None,
        }


def _git(
    args: list[str],
    cwd: str | Path | None = None,
    timeout: int = 120,
) -> tuple[int, str, str]:
    """Run a git command without a shell. Returns (rc, stdout, stderr)."""
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(cwd) if cwd else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"git timeout after {timeout}s: {' '.join(args)}"
    except OSError as exc:
        return -1, "", f"git not runnable: {exc}"


def ensure_clone(
    project_url: str,
    cache_root: str | Path = DEFAULT_CACHE_ROOT,
    timeout: int = CLONE_TIMEOUT_DEFAULT,
) -> tuple[Path | None, str | None]:
    """Ensure a cached full clone of ``project_url`` exists. Returns (path, err).

    Reuses an existing clone; otherwise clones into ``<cache_root>/<slug>``.
    On failure returns ``(None, reason)``.
    """
    slug = repo_cache_key(project_url)
    if not slug:
        return None, "bad_url"
    cache_root = Path(cache_root)
    dest = cache_root / slug
    if (dest / ".git").is_dir():
        return dest, None  # reuse existing cache
    cache_root.mkdir(parents=True, exist_ok=True)
    # Clone into a temp dir first, then atomically rename, so an interrupted
    # clone never leaves a half-populated cache entry.
    tmp = Path(tempfile.mkdtemp(prefix="cpptf_clone_", dir=str(cache_root)))
    rc, _out, err = _git(["clone", project_url, str(tmp / "repo")], timeout=timeout)
    if rc != 0:
        shutil.rmtree(tmp, ignore_errors=True)
        return None, f"clone_failed: {err.strip()[:500]}"
    (tmp / "repo").rename(dest)
    shutil.rmtree(tmp, ignore_errors=True)
    return dest, None


def _parent_count(cache_dir: Path, commit_id: str) -> int | None:
    """Number of parents of ``commit_id`` (None if it cannot be read)."""
    rc, out, _err = _git(
        ["rev-list", "--parents", "-n", "1", commit_id], cwd=cache_dir
    )
    if rc != 0 or not out.strip():
        return None
    return len(out.split()) - 1


def resolve_commit_sha(
    cache_dir: Path,
    meta: RepoMetadata,
) -> tuple[str | None, str | None]:
    """Resolve the concrete SHA to check out for ``meta``. Returns (sha, err).

    Honors ``commit_id`` semantics: ``func_fixed`` -> the fix commit;
    ``func_vuln`` -> its single parent. Root/merge commits are refused.
    """
    commit_id = meta.commit_id
    if not commit_id:
        return None, "no_commit_id"

    if meta.revision_relation == REL_FIX:
        target = commit_id
    elif meta.revision_relation == REL_PARENT:
        nparents = _parent_count(cache_dir, commit_id)
        if nparents is None:
            return None, f"revision_not_found: {commit_id}"
        if nparents == 0:
            return None, "no_parent"        # root commit, nothing to validate
        if nparents > 1:
            return None, "merge_commit"     # ambiguous parent; do not guess
        target = f"{commit_id}^1"
    else:
        return None, "unknown_relation"

    rc, out, _err = _git(["rev-parse", "--verify", f"{target}^{{commit}}"], cwd=cache_dir)
    if rc != 0 or not out.strip():
        return None, f"revision_not_found: {target}"
    return out.strip(), None


def create_workspace(cache_dir: Path, commit_sha: str) -> tuple[Workspace | None, str | None]:
    """Add a detached ``git worktree`` checked out at ``commit_sha``."""
    temp_parent = Path(tempfile.mkdtemp(prefix="cpptf_ws_"))
    ws_path = temp_parent / "wt"  # worktree add requires a non-existing path
    rc, _out, err = _git(
        ["worktree", "add", "--detach", str(ws_path), commit_sha],
        cwd=cache_dir,
    )
    if rc != 0:
        shutil.rmtree(temp_parent, ignore_errors=True)
        return None, f"worktree_failed: {err.strip()[:500]}"
    return (
        Workspace(
            root=ws_path,
            commit_sha=commit_sha,
            cache_dir=cache_dir,
            _temp_parent=temp_parent,
        ),
        None,
    )


def provision(
    meta: RepoMetadata,
    cache_root: str | Path = DEFAULT_CACHE_ROOT,
    clone_timeout: int = CLONE_TIMEOUT_DEFAULT,
) -> ProvisionResult:
    """Full provisioning: ensure clone -> resolve SHA -> isolated worktree."""
    if not meta.project_url:
        return ProvisionResult("error", error="no_project_url")

    cache_dir, err = ensure_clone(meta.project_url, cache_root, clone_timeout)
    if cache_dir is None:
        return ProvisionResult("error", error=err)

    sha, err = resolve_commit_sha(cache_dir, meta)
    if sha is None:
        return ProvisionResult("error", error=err)

    ws, err = create_workspace(cache_dir, sha)
    if ws is None:
        return ProvisionResult("error", error=err, commit_sha=sha)

    return ProvisionResult("ok", workspace=ws, commit_sha=sha)


def cleanup(workspace: Workspace | None) -> None:
    """Remove the worktree and its temp parent. Best-effort, never raises."""
    if workspace is None:
        return
    _git(
        ["worktree", "remove", "--force", str(workspace.root)],
        cwd=workspace.cache_dir,
    )
    shutil.rmtree(workspace._temp_parent, ignore_errors=True)

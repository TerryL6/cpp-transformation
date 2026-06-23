"""Run a build recipe in a checked-out workspace, with timeout and log capture.

This layer is deliberately *mechanical*: it runs the recipe's ``setup`` then
``build`` commands in order (no shell), captures combined stdout/stderr, and
reports a structured :class:`BuildResult`. It does **not** decide
``baseline_failed`` vs ``failed`` - that adjudication compares a baseline build
against a transformed build and lives in :mod:`cpp_transform.repo.classify`.

Status meanings:

* ``passed``  - every command exited 0.
* ``failed``  - a command ran and exited non-zero (e.g. a compile error).
* ``timeout`` - a command exceeded the per-command timeout.
* ``error``   - a command could not be launched (missing tool / bad workdir).
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from .recipes import BUILD_TIMEOUT_DEFAULT, BuildRecipe

# Cap captured log size so a runaway build cannot blow up memory / logs.
_MAX_LOG_CHARS = 200_000


@dataclass
class BuildResult:
    status: str                     # passed | failed | timeout | error
    returncode: int | None = None
    failed_stage: str | None = None  # e.g. "setup[1]" / "build[0]"
    failed_cmd: list[str] | None = None
    log: str = ""
    duration_s: float = 0.0

    @property
    def ok(self) -> bool:
        return self.status == "passed"

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "returncode": self.returncode,
            "failed_stage": self.failed_stage,
            "failed_cmd": list(self.failed_cmd) if self.failed_cmd else None,
            "duration_s": round(self.duration_s, 3),
        }


def _run_cmd(
    argv: list[str], cwd: Path, timeout: int
) -> tuple[int | None, str, str]:
    """Run one command. Returns (returncode, output, kind).

    ``kind`` is "ok" (ran to completion), "timeout", or "launch_error".
    ``returncode`` is None for timeout/launch_error.
    """
    try:
        proc = subprocess.run(
            argv,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout or "", "ok"
    except subprocess.TimeoutExpired as exc:
        partial = exc.output or ""
        if isinstance(partial, bytes):
            partial = partial.decode("utf-8", "replace")
        return None, partial, "timeout"
    except OSError as exc:
        return None, f"{exc}", "launch_error"


def run_build(
    workspace_root: str | Path,
    recipe: BuildRecipe,
    timeout: int | None = None,
) -> BuildResult:
    """Run ``recipe`` in ``workspace_root``; stop at the first non-success."""
    per_cmd_timeout = timeout or recipe.timeout or BUILD_TIMEOUT_DEFAULT
    workdir = Path(workspace_root) / recipe.workdir
    chunks: list[str] = []
    started = time.monotonic()

    def _finish(status, rc=None, stage=None, cmd=None) -> BuildResult:
        log = "".join(chunks)
        if len(log) > _MAX_LOG_CHARS:
            log = log[:_MAX_LOG_CHARS] + "\n...[truncated]...\n"
        return BuildResult(
            status=status,
            returncode=rc,
            failed_stage=stage,
            failed_cmd=cmd,
            log=log,
            duration_s=time.monotonic() - started,
        )

    if not workdir.is_dir():
        return _finish("error", stage="workdir", cmd=[str(workdir)])

    stages = [("setup", recipe.setup), ("build", recipe.build)]
    for stage_name, cmds in stages:
        for i, argv in enumerate(cmds):
            label = f"{stage_name}[{i}]"
            chunks.append(f"\n$ {' '.join(argv)}\n")
            rc, output, kind = _run_cmd(argv, workdir, per_cmd_timeout)
            chunks.append(output)
            if kind == "timeout":
                return _finish("timeout", stage=label, cmd=argv)
            if kind == "launch_error":
                return _finish("error", stage=label, cmd=argv)
            if rc != 0:
                return _finish("failed", rc=rc, stage=label, cmd=argv)

    return _finish("passed", rc=0)

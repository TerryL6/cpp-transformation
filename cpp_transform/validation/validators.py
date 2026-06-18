"""Validators.

Layers (kept clearly separated, never conflated):
  * srcml_reparse  : transformed source still parses with srcML  (REQUIRED)
  * structural     : transform-specific assertion (handled by the transform)
  * compiler       : compiler-abstraction syntax check, clang/clang++ preferred,
                     gcc/g++ fallback. Compared against the ORIGINAL snippet so
                     isolated snippets that never compile are reported "skipped"
                     rather than "failed"; only an original-passes/new-fails
                     delta is a real regression.
  * applied        : the output actually differs from the input

We do NOT claim semantic or vulnerability preservation here; those are assumed
by construction and left to downstream empirical checks (CodeQL / LLM).
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from ..frontends.base import Frontend, FrontendError

_COMPILERS = {
    "C": [("clang", "c"), ("gcc", "c")],
    "C++": [("clang++", "c++"), ("g++", "c++")],
}


def normalize_ws(s: str) -> str:
    return " ".join(s.split())


# -- srcML round trip & reparse --------------------------------------------
def roundtrip_metrics(frontend: Frontend, code: str, language: str) -> dict:
    """Parse then unparse with no transform; record fidelity metrics.

    We do not assume srcML is perfectly lossless on every snippet; this records
    exact-text equality, normalized equality, reparse success, and a diff flag.
    """
    out: dict = {
        "exact_equal": False,
        "normalized_equal": False,
        "reparse_ok": False,
        "error": None,
    }
    try:
        unit = frontend.parse(code, language)
        restored = frontend.unparse(unit)
        out["exact_equal"] = restored == code
        out["normalized_equal"] = normalize_ws(restored) == normalize_ws(code)
        # reparse the unparsed output
        frontend.parse(restored, language)
        out["reparse_ok"] = True
    except FrontendError as exc:
        out["error"] = str(exc)
    return out


def srcml_reparse(frontend: Frontend, code: str, language: str) -> dict:
    try:
        unit = frontend.parse(code, language)
        ok = unit is not None and len(unit) > 0
        return {"status": "passed" if ok else "failed"}
    except FrontendError as exc:
        return {"status": "failed", "error": str(exc)}


# -- compiler abstraction ---------------------------------------------------
class CompilerValidator:
    def __init__(self, language: str) -> None:
        self.language = language
        self.tool: str | None = None
        self.x_lang: str | None = None
        for tool, xlang in _COMPILERS.get(language, []):
            if shutil.which(tool):
                self.tool = tool
                self.x_lang = xlang
                break

    @property
    def available(self) -> bool:
        return self.tool is not None

    def _compile_rc(self, code: str) -> int:
        suffix = ".cpp" if self.language == "C++" else ".c"
        with tempfile.NamedTemporaryFile(
            "w", suffix=suffix, delete=False, encoding="utf-8"
        ) as fh:
            fh.write(code)
            path = fh.name
        try:
            proc = subprocess.run(
                [self.tool, "-fsyntax-only", "-w", "-x", self.x_lang, path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=60,
            )
            return proc.returncode
        except (subprocess.TimeoutExpired, OSError):
            return -1
        finally:
            Path(path).unlink(missing_ok=True)

    def validate(self, original: str, transformed: str) -> dict:
        if not self.available:
            return {"status": "unavailable", "tool": None}
        orig_rc = self._compile_rc(original)
        new_rc = self._compile_rc(transformed)
        if orig_rc == 0 and new_rc == 0:
            status = "passed"
        elif orig_rc != 0 and new_rc != 0:
            status = "skipped"  # snippet not independently compilable
        elif orig_rc == 0 and new_rc != 0:
            status = "failed"  # transform introduced a syntax regression
        else:
            status = "passed"  # original failed, transformed compiles
        return {
            "status": status,
            "tool": self.tool,
            "original_rc": orig_rc,
            "transformed_rc": new_rc,
        }

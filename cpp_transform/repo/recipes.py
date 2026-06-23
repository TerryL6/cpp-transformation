"""Build-recipe abstraction, auto-detection, and per-project overrides.

A :class:`BuildRecipe` describes how to build a checked-out repository: a list of
``setup`` commands (configure / cmake / autogen ...) followed by ``build``
commands (make ...), all run **without a shell** (each command is an argv list)
from ``workdir`` (relative to the repo root).

Per the V3 decisions, recipe resolution is **auto-detection first** (autotools /
cmake / make) with a **hand-written override** for the pilot repository. Missing
or unknown build systems return ``None`` so the caller records
``environment_error`` rather than guessing.

Detection only inspects marker files on disk, so it is fully offline-testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# Default per-command build timeout (seconds); overridable at the run level.
BUILD_TIMEOUT_DEFAULT = 600


@dataclass
class BuildRecipe:
    """How to build a repository. Commands are argv lists (no shell)."""

    name: str                                       # build system / override name
    setup: list[list[str]] = field(default_factory=list)
    build: list[list[str]] = field(default_factory=list)
    workdir: str = "."                              # relative to repo root
    timeout: int | None = None                      # per-command; None -> run default
    source: str = "detected"                        # "detected" | "override"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "setup": [list(c) for c in self.setup],
            "build": [list(c) for c in self.build],
            "workdir": self.workdir,
            "timeout": self.timeout,
            "source": self.source,
        }


# -- per-project overrides (hand-written fallback) -------------------------
# A declarative table of build quirks that auto-detection cannot infer (special
# configure flags, an alternate build system, ...). Adding a repository is one
# row here, not new code. Keyed by the dataset ``project`` name; each value
# supplies ``setup`` / ``build`` command lists (argv, no shell).
RECIPE_OVERRIDES: dict[str, dict] = {
    # The git checkout ships CMakeLists.txt alongside autotools sources. CMake
    # needs only gcc+cmake+make, vs autogen.sh+autotools (autoconf/automake/
    # libtool). Pure C, self-contained, fast.
    "oniguruma": {
        "setup": [["cmake", "-S", ".", "-B", "build"]],
        "build": [["cmake", "--build", "build"]],
    },
    # --disable-asm drops both the external nasm/yasm dependency and the GCC
    # inline asm (old FFmpeg x86 inline asm is rejected by modern binutils),
    # giving a slower but fully buildable C-only configuration with no sudo.
    "FFmpeg": {
        "setup": [["./configure", "--disable-asm"]],
        "build": [["make", "-j8"]],
    },
}


def _exists(root: Path, *names: str) -> bool:
    return any((root / n).exists() for n in names)


def detect_recipe(repo_root: str | Path) -> BuildRecipe | None:
    """Detect a build recipe from marker files in a checked-out repo root.

    Priority: existing ``configure`` -> ``autogen.sh`` -> ``configure.ac/.in``
    (autotools) -> ``CMakeLists.txt`` (cmake) -> a top-level ``Makefile``. Returns
    ``None`` when no known build system is recognized.
    """
    root = Path(repo_root)
    if not root.is_dir():
        return None

    if _exists(root, "configure"):
        return BuildRecipe(
            name="autotools",
            setup=[["./configure"]],
            build=[["make"]],
        )
    if _exists(root, "autogen.sh"):
        return BuildRecipe(
            name="autotools-autogen",
            setup=[["./autogen.sh"], ["./configure"]],
            build=[["make"]],
        )
    if _exists(root, "configure.ac", "configure.in"):
        return BuildRecipe(
            name="autotools-autoreconf",
            setup=[["autoreconf", "-fi"], ["./configure"]],
            build=[["make"]],
        )
    if _exists(root, "CMakeLists.txt"):
        return BuildRecipe(
            name="cmake",
            setup=[["cmake", "-S", ".", "-B", "build"]],
            build=[["cmake", "--build", "build"]],
        )
    if _exists(root, "Makefile", "GNUmakefile"):
        return BuildRecipe(
            name="make",
            setup=[],
            build=[["make"]],
        )
    return None


def get_recipe(
    repo_root: str | Path,
    project: str | None = None,
    timeout: int | None = None,
) -> BuildRecipe | None:
    """Resolve a recipe: per-project override first, else auto-detection.

    ``timeout`` (when given) is stamped onto the returned recipe so the build
    layer can enforce a per-command limit.
    """
    recipe: BuildRecipe | None = None
    spec = RECIPE_OVERRIDES.get(project) if project else None
    if spec is not None:
        recipe = BuildRecipe(
            name=spec.get("name", project),
            setup=[list(c) for c in spec.get("setup", [])],
            build=[list(c) for c in spec.get("build", [])],
            workdir=spec.get("workdir", "."),
            source="override",
        )
    if recipe is None:
        recipe = detect_recipe(repo_root)
    if recipe is not None and timeout is not None:
        recipe.timeout = timeout
    return recipe

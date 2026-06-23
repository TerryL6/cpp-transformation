"""Build-recipe detection + overrides (offline; only inspects marker files)."""

from __future__ import annotations

from cpp_transform.repo.recipes import (
    BUILD_TIMEOUT_DEFAULT,
    detect_recipe,
    get_recipe,
)


def _touch(root, name: str) -> None:
    (root / name).write_text("", encoding="utf-8")


def test_detect_configure_autotools(tmp_path):
    _touch(tmp_path, "configure")
    r = detect_recipe(tmp_path)
    assert r.name == "autotools"
    assert r.setup == [["./configure"]] and r.build == [["make"]]


def test_detect_autogen(tmp_path):
    _touch(tmp_path, "autogen.sh")
    r = detect_recipe(tmp_path)
    assert r.name == "autotools-autogen"
    assert ["./autogen.sh"] in r.setup


def test_detect_autoreconf(tmp_path):
    _touch(tmp_path, "configure.ac")
    r = detect_recipe(tmp_path)
    assert r.name == "autotools-autoreconf"
    assert ["autoreconf", "-fi"] in r.setup


def test_detect_cmake(tmp_path):
    _touch(tmp_path, "CMakeLists.txt")
    r = detect_recipe(tmp_path)
    assert r.name == "cmake"


def test_detect_plain_make(tmp_path):
    _touch(tmp_path, "Makefile")
    r = detect_recipe(tmp_path)
    assert r.name == "make" and r.build == [["make"]]


def test_detect_unknown_returns_none(tmp_path):
    assert detect_recipe(tmp_path) is None


def test_detect_priority_configure_over_autogen(tmp_path):
    _touch(tmp_path, "configure")
    _touch(tmp_path, "autogen.sh")
    assert detect_recipe(tmp_path).name == "autotools"


def test_override_wins_over_detection(tmp_path):
    # The override forces cmake even though detection would pick autotools first
    # (autogen.sh is checked before CMakeLists.txt).
    _touch(tmp_path, "autogen.sh")
    r = get_recipe(tmp_path, project="oniguruma")
    assert r.source == "override" and r.name == "oniguruma"
    assert ["cmake", "-S", ".", "-B", "build"] in r.setup


def test_ffmpeg_override_full_build_no_precheck(tmp_path):
    # Declarative override: configure with --disable-asm (no external deps),
    # then a single full make as the verdict. No per-file pre-check.
    r = get_recipe(tmp_path, project="FFmpeg")
    assert r.source == "override" and r.name == "FFmpeg"
    assert r.setup == [["./configure", "--disable-asm"]]
    assert r.build == [["make", "-j8"]]


def test_get_recipe_falls_back_to_detection(tmp_path):
    _touch(tmp_path, "Makefile")
    r = get_recipe(tmp_path, project="unknown-project")
    assert r.source == "detected" and r.name == "make"


def test_get_recipe_stamps_timeout(tmp_path):
    _touch(tmp_path, "configure")
    r = get_recipe(tmp_path, timeout=BUILD_TIMEOUT_DEFAULT)
    assert r.timeout == BUILD_TIMEOUT_DEFAULT


def test_get_recipe_unknown_returns_none(tmp_path):
    assert get_recipe(tmp_path, project="unknown-project") is None

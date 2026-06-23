"""Build-runner tests using coreutils (true/false/sleep); offline and fast."""

from __future__ import annotations

from cpp_transform.repo.build import run_build
from cpp_transform.repo.recipes import BuildRecipe


def _recipe(setup=None, build=None, timeout=None) -> BuildRecipe:
    return BuildRecipe(
        name="test", setup=setup or [], build=build or [], timeout=timeout
    )


def test_passed(tmp_path):
    r = run_build(tmp_path, _recipe(build=[["true"]]))
    assert r.status == "passed" and r.ok and r.returncode == 0


def test_failed_nonzero(tmp_path):
    r = run_build(tmp_path, _recipe(build=[["false"]]))
    assert r.status == "failed" and r.returncode != 0
    assert r.failed_stage == "build[0]" and r.failed_cmd == ["false"]


def test_setup_runs_before_build_and_stops_on_failure(tmp_path):
    # setup[1] fails, so build must never run.
    r = run_build(tmp_path, _recipe(setup=[["true"], ["false"]], build=[["true"]]))
    assert r.status == "failed" and r.failed_stage == "setup[1]"


def test_timeout(tmp_path):
    r = run_build(tmp_path, _recipe(build=[["sleep", "5"]], timeout=1))
    assert r.status == "timeout" and r.failed_stage == "build[0]"


def test_launch_error_missing_tool(tmp_path):
    r = run_build(tmp_path, _recipe(build=[["definitely_not_a_real_cmd_xyz"]]))
    assert r.status == "error" and r.failed_stage == "build[0]"


def test_bad_workdir(tmp_path):
    r = _recipe(build=[["true"]])
    r.workdir = "does_not_exist"
    res = run_build(tmp_path, r)
    assert res.status == "error" and res.failed_stage == "workdir"


def test_log_captures_command_and_output(tmp_path):
    r = run_build(tmp_path, _recipe(build=[["echo", "hello_build"]]))
    assert r.status == "passed"
    assert "echo hello_build" in r.log and "hello_build" in r.log


def test_workdir_relative_to_root(tmp_path):
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "marker").write_text("x", encoding="utf-8")
    rec = _recipe(build=[["ls", "marker"]])
    rec.workdir = "sub"
    res = run_build(tmp_path, rec)
    assert res.status == "passed" and "marker" in res.log

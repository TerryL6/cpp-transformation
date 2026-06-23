"""Whole-function placement tests (offline, pure text)."""

from __future__ import annotations

from cpp_transform.repo.placement import locate_function, place_function

_FILE = """\
#include <stdio.h>

extern int
foo(int a, int b)
{
  return a + b;
}

int main(void) { return foo(1, 2); }
"""

# func text begins at the name line, as in the SVEN dataset (return type on the
# previous line is NOT part of the function field).
_ORIG = "foo(int a, int b)\n{\n  return a + b;\n}"
_NEW = "foo(int a, int b)\n{\n  int __chain = a + b;\n  return __chain;\n}"


def test_locate_exact(tmp_path):
    status, hits, blen = locate_function(_FILE, _ORIG)
    assert status == "exact" and len(hits) == 1 and blen == 4
    assert hits[0] == 3  # 0-based line index of "foo(int a, int b)"


def test_place_replaces_unique(tmp_path):
    f = tmp_path / "f.c"
    f.write_text(_FILE, encoding="utf-8")
    res = place_function(f, _ORIG, _NEW)
    assert res.status == "placed" and res.mapping_status == "exact"
    assert res.start_line == 4 and res.end_line == 7  # 1-based inclusive
    txt = f.read_text(encoding="utf-8")
    assert "__chain" in txt
    assert "#include <stdio.h>" in txt and "int main(void)" in txt  # rest intact


def test_trailing_whitespace_insensitive(tmp_path):
    f = tmp_path / "f.c"
    # add trailing spaces to a line in the file
    dirty = _FILE.replace("  return a + b;", "  return a + b;   ")
    f.write_text(dirty, encoding="utf-8")
    res = place_function(f, _ORIG, _NEW)
    assert res.status == "placed" and res.mapping_status == "exact_normalized"


def test_not_found_is_ambiguous(tmp_path):
    f = tmp_path / "f.c"
    f.write_text(_FILE, encoding="utf-8")
    res = place_function(f, "bar(void)\n{\n  return 0;\n}", _NEW)
    assert res.status == "skipped_ambiguous" and res.mapping_status == "not_found"
    # file unchanged
    assert f.read_text(encoding="utf-8") == _FILE


def test_multiple_matches_is_ambiguous(tmp_path):
    f = tmp_path / "f.c"
    block = "dup(void)\n{\n  return 0;\n}"
    f.write_text(block + "\n\n" + block + "\n", encoding="utf-8")
    res = place_function(f, block, "dup(void)\n{\n  return 1;\n}")
    assert res.status == "skipped_ambiguous" and res.mapping_status == "multiple"


def test_read_error_on_missing_file(tmp_path):
    res = place_function(tmp_path / "nope.c", _ORIG, _NEW)
    assert res.status == "error" and "read_failed" in res.detail

"""Dataset layer: language detection priority, field detection, JSONL streaming."""

from __future__ import annotations

from cpp_transform.io.dataset import (
    detect_code_fields,
    detect_language,
    iter_jsonl,
)


def test_language_priority_explicit_wins():
    d = detect_language({"language": "C", "file_name": "x.cpp"},
                        explicit="C++", file_name="x.c")
    assert d.language == "C++" and d.source == "explicit"


def test_language_from_field():
    d = detect_language({"lang": "c++"})
    assert d.language == "C++" and d.source == "field"


def test_language_from_extension():
    d = detect_language({"file_name": "a/b/c.c"})
    assert d.language == "C" and d.source == "extension"


def test_language_unresolved_no_silent_default():
    d = detect_language({"func_vuln": "..."})
    assert d.language is None and d.source == "unresolved"


def test_language_h_is_ambiguous():
    d = detect_language({"file_name": "foo.h"})
    assert d.language is None


def test_detect_code_fields_aliases():
    assert detect_code_fields({"func_vuln": "x"}, "vuln") == ["func_vuln"]
    assert detect_code_fields({"vuln_func": "x"}, "vuln") == ["vuln_func"]
    both = detect_code_fields({"func_vuln": "a", "func_fixed": "b"}, "both")
    assert set(both) == {"func_vuln", "func_fixed"}


def test_iter_jsonl_isolates_bad_lines(tmp_path):
    p = tmp_path / "data.jsonl"
    p.write_text('{"a": 1}\nnot json\n{"b": 2}\n', encoding="utf-8")
    items = list(iter_jsonl(p))
    assert len(items) == 3
    assert items[0].record == {"a": 1}
    assert items[1].error is not None and items[1].record is None
    assert items[2].record == {"b": 2}

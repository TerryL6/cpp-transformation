"""Repo metadata parsing + revision resolution (pure Python, no network)."""

from __future__ import annotations

from cpp_transform.repo.metadata import (
    REL_FIX,
    REL_PARENT,
    REL_UNKNOWN,
    classify_field,
    parse_repo_metadata,
    repo_cache_key,
    resolve_checkout_revision,
)

_FULL = {
    "project": "oniguruma",
    "project_url": "https://github.com/kkos/oniguruma",
    "commit_id": "0f7f61ed1b7b697e283e37bd2d731d0bd57adb55",
    "file_name": "src/regext.c",
    "func_name": "onig_new_deluxe",
    "vul_type": "cwe-416",
}


def test_func_vuln_checks_out_parent():
    d = parse_repo_metadata(_FULL, target_field="func_vuln")
    assert d.sufficient and d.reason == "ok"
    assert d.metadata.revision_relation == REL_PARENT
    assert d.metadata.checkout_revision == _FULL["commit_id"] + "^1"


def test_func_fixed_checks_out_fix_commit():
    d = parse_repo_metadata(_FULL, target_field="func_fixed")
    assert d.sufficient
    assert d.metadata.revision_relation == REL_FIX
    assert d.metadata.checkout_revision == _FULL["commit_id"]


def test_alias_fields_classified():
    assert classify_field("vuln_func") == REL_PARENT
    assert classify_field("fixed_func") == REL_FIX
    assert classify_field("something_else") == REL_UNKNOWN
    assert classify_field(None) == REL_UNKNOWN


def test_resolve_checkout_revision():
    assert resolve_checkout_revision("abc", REL_PARENT) == "abc^1"
    assert resolve_checkout_revision("abc", REL_FIX) == "abc"
    assert resolve_checkout_revision("abc", REL_UNKNOWN) is None
    assert resolve_checkout_revision(None, REL_PARENT) is None


def test_missing_fields_make_insufficient():
    d = parse_repo_metadata({"project": "x"}, target_field="func_vuln")
    assert not d.sufficient
    for f in ("project_url", "commit_id", "file_name", "func_name"):
        assert f in d.missing
    assert d.reason.startswith("missing:")


def test_unknown_field_relation_blocks_when_commit_present():
    # A commit exists but the field cannot be classified -> we cannot decide
    # parent vs fix, so it is reported as missing the relation.
    rec = dict(_FULL)
    d = parse_repo_metadata(rec, target_field="weird_field")
    assert d.metadata.revision_relation == REL_UNKNOWN
    assert d.metadata.checkout_revision is None
    assert "revision_relation" in d.missing
    assert not d.sufficient


def test_filename_alias_and_blank_handling():
    rec = dict(_FULL)
    del rec["file_name"]
    rec["filename"] = "src/regext.c"
    rec["func_name"] = "   "  # blank -> treated as missing
    d = parse_repo_metadata(rec, target_field="func_vuln")
    assert d.metadata.file_name == "src/regext.c"
    assert d.metadata.func_name is None
    assert "func_name" in d.missing


def test_repo_cache_key():
    assert repo_cache_key("https://github.com/kkos/oniguruma") == "github.com_kkos_oniguruma"
    assert repo_cache_key("https://github.com/kkos/oniguruma.git") == "github.com_kkos_oniguruma"
    assert repo_cache_key("git://example.com/a/b/") == "example.com_a_b"
    assert repo_cache_key(None) is None

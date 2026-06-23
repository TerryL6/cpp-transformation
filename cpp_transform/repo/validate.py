"""Orchestrate one repository-level validation attempt end to end.

Ties the stages together: metadata -> provision -> baseline build -> placement
-> transformed build -> classify, then writes a build log and cleans up the
isolated workspace. Returns a single ``repo_validation`` dict ready to attach to
a :class:`~cpp_transform.model.result.TransformResult`.

Designed to be called once per *successful* transform attempt that carries
repository context; everything is best-effort and never raises into the batch.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import provision as P
from .build import run_build
from .classify import classify
from .metadata import parse_repo_metadata, repo_cache_key
from .placement import place_function
from .recipes import BUILD_TIMEOUT_DEFAULT, get_recipe


@dataclass
class RepoValidateConfig:
    cache_root: str | Path = P.DEFAULT_CACHE_ROOT
    build_timeout: int = BUILD_TIMEOUT_DEFAULT
    clone_timeout: int = P.CLONE_TIMEOUT_DEFAULT
    log_dir: str | Path | None = None       # where build logs are written


def _write_build_log(
    config: RepoValidateConfig,
    meta,
    target_field: str | None,
    sections: list[tuple[str, str]],
) -> str | None:
    """Write concatenated build sections to the log dir; return the path."""
    if config.log_dir is None:
        return None
    log_dir = Path(config.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    slug = repo_cache_key(meta.project_url) or (meta.project or "repo")
    commit = (meta.commit_id or "nocommit")[:12]
    name = f"{slug}_{commit}_{target_field or 'field'}.log"
    path = log_dir / name
    body = []
    for title, text in sections:
        body.append(f"===== {title} =====\n{text}\n")
    path.write_text("\n".join(body), encoding="utf-8")
    return str(path)


def validate_record(
    record: dict,
    target_field: str | None,
    original_code: str,
    transformed_code: str,
    config: RepoValidateConfig | None = None,
) -> dict:
    """Run repository-level validation for one (record x field) attempt."""
    config = config or RepoValidateConfig()
    decision = parse_repo_metadata(record, target_field)
    meta = decision.metadata

    base = {
        "project": meta.project,
        "commit": meta.commit_id,
        "checkout_revision": meta.checkout_revision,
        "file": meta.file_name,
        "func": meta.func_name,
        "build_log_ref": None,
        "matched_span": None,
        "recipe": None,
    }

    if not decision.sufficient:
        result = classify(metadata_sufficient=False)
        result["detail"] = decision.reason
        return {**base, **result}

    prov = P.provision(meta, config.cache_root, config.clone_timeout)
    if prov.status != "ok":
        result = classify(metadata_sufficient=True, provision_error=prov.error)
        return {**base, **result}

    base["commit_sha"] = prov.commit_sha
    baseline = placement = transformed = None
    sections: list[tuple[str, str]] = []
    try:
        recipe = get_recipe(prov.workspace.root, meta.project, config.build_timeout)
        if recipe is None:
            result = {
                "status": "environment_error", "baseline_status": None,
                "mapping_status": None, "detail": "no_build_system",
            }
            return {**base, **result}
        base["recipe"] = recipe.name

        baseline = run_build(prov.workspace.root, recipe, config.build_timeout)
        sections.append(("baseline", baseline.log))

        if baseline.status == "passed":
            target_file = Path(prov.workspace.root) / (meta.file_name or "")
            placement = place_function(target_file, original_code, transformed_code)
            if placement.status == "placed":
                base["matched_span"] = {
                    "file": meta.file_name,
                    "start_line": placement.start_line,
                    "end_line": placement.end_line,
                }
                transformed = run_build(prov.workspace.root, recipe, config.build_timeout)
                sections.append(("transformed", transformed.log))

        result = classify(
            metadata_sufficient=True,
            baseline=baseline,
            placement=placement,
            transformed=transformed,
        )
        base["build_log_ref"] = _write_build_log(config, meta, target_field, sections)
        return {**base, **result}
    finally:
        P.cleanup(prov.workspace)

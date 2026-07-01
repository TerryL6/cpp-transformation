"""Core pipeline: apply one transform to one piece of source code.

Stages: parse -> locate candidates -> pick -> tree transform -> unparse ->
validate. On any failure the transformed code is rolled back to the original and
the result is marked ``failed`` (so a batch never produces broken output).
"""

from __future__ import annotations

from .codegen import unparse as do_unparse
from .frontends.base import Frontend, FrontendError
from .location.model import apply_input_context, changed_line_spans
from .model.context import TransformContext
from .model.result import TransformResult
from .pick.strategies import get_strategy
from .transforms.base import Transformation
from .validation.validators import CompilerValidator, srcml_reparse


def apply_transform(
    frontend: Frontend,
    code: str,
    language: str,
    transform: Transformation,
    pick: str = "first",
    seed: int | None = 42,
    target_field: str | None = None,
    compiler_validate: bool = False,
    input_kind: str = "snippet",
    source: str | None = None,
    anchors: list | None = None,
) -> TransformResult:
    result = TransformResult(
        name=transform.name,
        family=transform.family,
        seed=seed,
        target_field=target_field,
        language=language,
        original_code=code,
        transformed_code=code,
    )

    # -- parse (with positions so locators can capture source locations) ----
    try:
        unit = frontend.parse(code, language, with_position=True)
    except FrontendError as exc:
        result.status = "failed"
        result.error = f"parse error: {exc}"
        return result
    ctx = TransformContext(
        unit,
        language,
        frontend,
        input_kind=input_kind,
        source=source,
    )

    # -- inject vulnerability anchors (V4, opt-in) --------------------------
    # Runs right after parse (positions still valid) and before any mutation, so
    # anchored nodes carry their BEFORE location. ``vuln_anchor`` is seeded with
    # before-only ``not_attempted`` blocks so every early-return path still
    # reports the anchors; the success path overwrites them with recovered
    # after-positions and a survival status.
    anchor_specs: list = []
    if anchors:
        from .anchor.builder import inject_anchors
        from .anchor.finalize import pending_blocks

        anchor_specs = inject_anchors(unit, anchors, input_kind, source)
        result.vuln_anchor = pending_blocks(anchor_specs)

    # -- locate + pick ------------------------------------------------------
    candidates = transform.find_candidates(ctx)
    if not candidates:
        result.status = "skipped"
        result.error = "no_candidates"
        return result
    result.candidate_count = len(candidates)
    # Enrich each eagerly-captured BEFORE position with input context
    # (source + relative_to) before any tree mutation makes the srcML pos:*
    # attributes stale.
    for cand in candidates:
        if cand.source_location is not None:
            apply_input_context(cand.source_location, input_kind, source)
    chosen = get_strategy(pick)(candidates, seed)
    if not chosen:
        result.status = "skipped"
        result.error = "pick_selected_none"
        return result
    result.selected_candidates = [c.to_dict(slim=True) for c in chosen]

    # -- transform (tree mutation) -----------------------------------------
    try:
        for cand in chosen:
            if not transform.can_apply(cand, ctx):
                continue
            transform.apply(cand, ctx)
    except Exception as exc:  # rollback on any mutation error
        result.status = "failed"
        result.error = f"apply error: {exc}"
        result.transformed_code = code
        return result

    # -- unparse ------------------------------------------------------------
    try:
        transformed = do_unparse(frontend, ctx.unit)
    except FrontendError as exc:
        result.status = "failed"
        result.error = f"unparse error: {exc}"
        result.transformed_code = code
        return result

    changed = transformed != code

    # -- validate -----------------------------------------------------------
    reparse = srcml_reparse(frontend, transformed, language)
    structural_ok = all(t_check(transform, c, ctx) for c in chosen)
    validation: dict = {
        "srcml_reparse": reparse,
        "structural": {"status": "passed" if structural_ok else "failed"},
        "applied": {"status": "passed" if changed else "failed"},
    }
    if compiler_validate:
        validation["compiler"] = CompilerValidator(language).validate(code, transformed)

    reparse_ok = reparse.get("status") == "passed"
    compiler_failed = (
        compiler_validate and validation["compiler"].get("status") == "failed"
    )
    ok = changed and reparse_ok and structural_ok and not compiler_failed

    if ok:
        result.status = "success"
        result.changed = True
        result.transformed_code = transformed
        # AFTER location (Option B): the changed line ranges in transformed-output
        # coordinates, derived by diff (transform-agnostic, line-level only).
        result.transformed_location = [
            s.to_dict() for s in changed_line_spans(code, transformed, source)
        ]
        # Recover where each anchor landed and classify its survival. Runs on the
        # mutated tree (``va:*`` still ride the surviving nodes); recovery probes
        # a throwaway copy, so the emitted output above is unaffected.
        if anchors:
            from .anchor.finalize import finalize_anchors

            result.vuln_anchor = finalize_anchors(
                anchor_specs, ctx.unit, frontend, language, source
            )
    else:
        result.status = "failed"
        result.transformed_code = code  # rollback
        reasons = []
        if not changed:
            reasons.append("no_change")
        if not reparse_ok:
            reasons.append("reparse_failed")
        if not structural_ok:
            reasons.append("structural_failed")
        if compiler_failed:
            reasons.append("compiler_regression")
        result.error = ",".join(reasons) or "unknown"
    result.validation = validation
    return result


def t_check(transform: Transformation, cand, ctx: TransformContext) -> bool:
    try:
        return transform.structural_check(cand, ctx)
    except Exception:
        return False


def run_repo_validation(result: TransformResult, record: dict, config) -> None:
    """Attach repository-level validation to ``result`` (V3, opt-in).

    Runs only when the lightweight transform actually changed code, since there
    is otherwise nothing to place back. Best-effort: any unexpected error is
    recorded as ``environment_error`` rather than breaking the batch. The repo
    subsystem is imported lazily so the core pipeline never depends on it.
    """
    if not (result.status == "success" and result.changed):
        return
    from .repo.validate import validate_record

    try:
        result.repo_validation = validate_record(
            record=record,
            target_field=result.target_field,
            original_code=result.original_code,
            transformed_code=result.transformed_code,
            config=config,
        )
    except Exception as exc:  # never let repo validation crash the batch
        result.repo_validation = {
            "status": "environment_error",
            "detail": f"unexpected: {exc}",
        }

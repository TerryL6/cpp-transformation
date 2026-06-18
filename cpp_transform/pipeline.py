"""Core pipeline: apply one transform to one piece of source code.

Stages: parse -> locate candidates -> pick -> tree transform -> unparse ->
validate. On any failure the transformed code is rolled back to the original and
the result is marked ``failed`` (so a batch never produces broken output).
"""

from __future__ import annotations

from .codegen import unparse as do_unparse
from .frontends.base import Frontend, FrontendError
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

    # -- parse --------------------------------------------------------------
    try:
        unit = frontend.parse(code, language)
    except FrontendError as exc:
        result.status = "failed"
        result.error = f"parse error: {exc}"
        return result
    ctx = TransformContext(unit, language, frontend)

    # -- locate + pick ------------------------------------------------------
    candidates = transform.find_candidates(ctx)
    if not candidates:
        result.status = "skipped"
        result.error = "no_candidates"
        return result
    chosen = get_strategy(pick)(candidates, seed)
    if not chosen:
        result.status = "skipped"
        result.error = "pick_selected_none"
        return result
    result.candidate = chosen[0].to_dict()

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

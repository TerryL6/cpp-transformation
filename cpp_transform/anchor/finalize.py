"""Assemble the ``vuln_anchor`` output blocks.

Ties together the three anchor stages into the metadata that lands on
``TransformResult.vuln_anchor``:

* :func:`pending_blocks` - before-only view, used at every early-return path
  (parse/skip/failure) so a ``vuln_anchor`` block always exists once anchoring
  was requested; each is ``not_attempted`` until recovery runs.
* :func:`finalize_anchors` - the success path: recover after-positions on the
  mutated tree and classify each anchor by how many nodes survived.
"""

from __future__ import annotations

from typing import Any

from lxml import etree

from ..frontends.base import Frontend
from .builder import AnchorSpec
from .classify import NOT_ATTEMPTED, classify
from .recover import recover_anchor_positions


def _block(
    spec: AnchorSpec,
    status: str,
    after: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": spec.id,
        "role": spec.role,
        "before": spec.before.to_dict() if spec.before else None,
        "after": after,
        "status": status,
        "detail": spec.detail,
    }


def pending_blocks(specs: list[AnchorSpec]) -> list[dict[str, Any]]:
    """Before-only blocks; every anchor is ``not_attempted`` for now."""
    return [_block(spec, NOT_ATTEMPTED) for spec in specs]


def finalize_anchors(
    specs: list[AnchorSpec],
    unit: etree._Element,
    frontend: Frontend,
    language: str,
    source: str | None = None,
) -> list[dict[str, Any]]:
    """Recover after-positions on ``unit`` and classify each anchor."""
    positions, counts = recover_anchor_positions(unit, frontend, language, source)
    blocks: list[dict[str, Any]] = []
    for spec in specs:
        if not spec.injected:
            blocks.append(_block(spec, NOT_ATTEMPTED))
            continue
        count = counts.get(spec.id, 0)
        status = classify(count)
        after = positions.get(spec.id)
        blocks.append(_block(spec, status, after.to_dict() if after else None))
    return blocks

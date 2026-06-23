"""Source-location tracking (V2).

Exposes the :class:`SourceLocation` value object plus helpers to build it from
srcML position attributes, annotate it with input context, and describe the
changed regions after a transform.
"""

from __future__ import annotations

from .model import (
    REL_FILE,
    REL_INPUT,
    REL_OUTPUT,
    REL_REPO,
    SourceLocation,
    apply_input_context,
    changed_line_spans,
    from_srcml_node,
)

__all__ = [
    "SourceLocation",
    "from_srcml_node",
    "changed_line_spans",
    "apply_input_context",
    "REL_INPUT",
    "REL_FILE",
    "REL_OUTPUT",
    "REL_REPO",
]

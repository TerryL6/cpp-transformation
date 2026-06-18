"""Unparsing helper.

Output source is produced exclusively by serializing the structured tree through
the frontend (srcML ``--unparse``). There is no byte-offset or string-splice
path: this function is the single, enforced exit from tree to source.
"""

from __future__ import annotations

from lxml import etree

from ..frontends.base import Frontend


def unparse(frontend: Frontend, unit: etree._Element) -> str:
    return frontend.unparse(unit)

"""Map surviving-anchor counts to a status enum.

The rule is intentionally conservative - we never *guess* which of several
surviving copies is "the" vulnerability:

* exactly 1 surviving node -> ``tracked``   (clean before -> after mapping)
* 0 surviving nodes         -> ``lost``      (the vuln node may be gone)
* >1 surviving nodes        -> ``ambiguous`` (a legit split we do not resolve)

``not_attempted`` is used when anchoring was requested but the anchor could not
be injected (e.g. the target line matched no statement node), or when the
transform never reached the recovery stage.
"""

from __future__ import annotations

TRACKED = "tracked"
LOST = "lost"
AMBIGUOUS = "ambiguous"
NOT_ATTEMPTED = "not_attempted"


def classify(found_count: int) -> str:
    """Map the number of surviving anchor nodes to a status."""
    if found_count == 1:
        return TRACKED
    if found_count == 0:
        return LOST
    return AMBIGUOUS

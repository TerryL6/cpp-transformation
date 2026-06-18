"""Shared pytest fixtures.

The whole suite needs a working ``srcml`` binary; if it is unavailable the
srcml-dependent tests are skipped (pure-Python tests like language detection
still run).
"""

from __future__ import annotations

import pytest

from cpp_transform.frontends.base import FrontendError
from cpp_transform.frontends.srcml_frontend import SrcmlFrontend


@pytest.fixture(scope="session")
def frontend() -> SrcmlFrontend:
    fe = SrcmlFrontend()
    try:
        fe.version()
    except FrontendError as exc:  # pragma: no cover
        pytest.skip(f"srcml unavailable: {exc}")
    return fe

"""Repository-level compilation validation (V3).

This subsystem is *additive*: it never rewrites the existing lightweight
validation. Given a dataset record with repository context (``project_url`` /
``commit_id`` / ``file_name`` / ``func_name``), it can fetch the repository,
check out the correct revision, build an unchanged baseline, place the
transformed function back, rebuild, and classify the outcome.

Modules:
  * :mod:`cpp_transform.repo.metadata` - parse record -> repo metadata and
    derive which revision to check out.
  * :mod:`cpp_transform.repo.recipes`  - build-recipe abstraction + detection.
  * (later) ``provision`` / ``build`` / ``placement`` / ``classify``.
"""

from __future__ import annotations

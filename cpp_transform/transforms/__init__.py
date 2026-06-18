"""Transformations and the global registry.

Importing this package registers all built-in transforms so the CLI, batch
runner, and reports can discover them by name with zero extra wiring.
"""

from .base import REGISTRY, Transformation, get_transform, register  # noqa: F401
from . import variable_chain  # noqa: F401  (registers VariableChain)
from . import macro_alias  # noqa: F401  (registers MacroAlias)

"""cpp_transform: a strict tree-to-tree C/C++ source transformation framework.

The framework parses C/C++ into a structured srcML XML representation, locates
transformation candidates, selects them with a pick strategy, mutates the
*structured tree* (never raw byte offsets), and unparses back to source via
srcML. See the project plan for the full design.
"""

__version__ = "0.1.0"

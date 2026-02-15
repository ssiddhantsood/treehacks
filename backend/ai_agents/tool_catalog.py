"""
Tool catalog grouped by category.

Order matters: basic editing tools first, then generative tools.
"""

from __future__ import annotations

from .agent import EDIT_TOOLS, SPEED_TOOLS
from .generative.agent import TOOLS as GENERATIVE_TOOLS


BASIC_EDIT_TOOLS = [*SPEED_TOOLS, *EDIT_TOOLS]

TOOL_CATEGORIES = [
    {
        "key": "basic_editing",
        "label": "Basic Editing Tools",
        "tools": BASIC_EDIT_TOOLS,
    },
    {
        "key": "generative",
        "label": "Generative Tools",
        "tools": GENERATIVE_TOOLS,
    },
]


__all__ = ["BASIC_EDIT_TOOLS", "GENERATIVE_TOOLS", "TOOL_CATEGORIES"]

"""Scaffolder service package — generates impl/ code skeleton."""
from .tech_stack_reader import ScaffoldConfig, read_scaffold_config
from .tree_builder import build_static_tree, SCAFFOLD_MARKER
from .llm import run_scaffolder_llm
from .rubric import ScaffoldRubric

__all__ = [
    "ScaffoldConfig",
    "read_scaffold_config",
    "build_static_tree",
    "SCAFFOLD_MARKER",
    "run_scaffolder_llm",
    "ScaffoldRubric",
]

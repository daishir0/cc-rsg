"""cc-rsg source-map v2 (role-typed, framework-aware, tree-sitter based).

Status: M0 — constitution (taxonomy) + schema 0.2.0 + three-layer skeleton.
Language extractors are added in later milestones (M2 TypeScript, M3 Python, ...).

Public surface:
    from source_map_v2 import build_source_map, SCHEMA_VERSION
"""

from __future__ import annotations

from .model import SCHEMA_VERSION, SourceMap, SourceUnit
from .pipeline import build_source_map

__all__ = ["build_source_map", "SourceMap", "SourceUnit", "SCHEMA_VERSION"]

"""cc-rsg source-map v2 — data model (source-map.json schema 0.2.0).

Backward compatible with 0.1.0: the legacy fields (id, path, line_range, kind,
name, signature, fingerprint) and ``stats.files_scanned`` are preserved.
New fields are *added*, never repurposed:
  - language, framework, role, tier        (role typing / framework awareness)
  - endpoint {method, path}                (only for role == "endpoint")
  - top-level: detected_frameworks, warnings
  - stats: by_role, by_language            (alongside the existing by_kind)
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from . import taxonomy

SCHEMA_VERSION = "0.2.0"


def fingerprint(text: str) -> str:
    return "sha1:" + hashlib.sha1(text.encode("utf-8", errors="replace")).hexdigest()[:16]


@dataclass
class SourceUnit:
    id: str
    path: str
    line_range: tuple[int, int]
    language: str
    role: str
    kind: str
    name: str
    signature: str = ""
    tier: str = "middle"
    framework: str | None = None
    endpoint: dict[str, Any] | None = None  # {"method": "GET", "path": "/x"} when role == "endpoint"
    fingerprint: str = ""

    def validate(self) -> None:
        """Enforce the constitution on a single unit."""
        if not taxonomy.is_valid_role(self.role):
            raise taxonomy.TaxonomyError(f"unit {self.id} has invalid role {self.role!r}")
        if self.tier not in taxonomy.TIERS:
            raise taxonomy.TaxonomyError(f"unit {self.id} has invalid tier {self.tier!r}")
        if self.endpoint is not None and self.role != "endpoint":
            raise taxonomy.TaxonomyError(
                f"unit {self.id} carries endpoint metadata but role is {self.role!r} (must be 'endpoint')"
            )

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.id,
            "path": self.path,
            "line_range": list(self.line_range),
            "language": self.language,
            "role": self.role,
            "table": taxonomy.table_for_role(self.role),
            "kind": self.kind,
            "tier": self.tier,
            "name": self.name,
            "signature": self.signature,
            "fingerprint": self.fingerprint,
        }
        if self.framework:
            d["framework"] = self.framework
        if self.endpoint is not None:
            d["endpoint"] = self.endpoint
        return d


@dataclass
class SourceMap:
    target_root: str
    detected_frameworks: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    units: list[SourceUnit] = field(default_factory=list)
    files_scanned: int = 0
    files_excluded: int = 0
    generated_at: str | None = None

    def compute_stats(self) -> dict[str, Any]:
        by_kind: dict[str, int] = {}
        by_role: dict[str, int] = {}
        by_language: dict[str, int] = {}
        for u in self.units:
            by_kind[u.kind] = by_kind.get(u.kind, 0) + 1
            by_role[u.role] = by_role.get(u.role, 0) + 1
            by_language[u.language] = by_language.get(u.language, 0) + 1
        return {
            "files_scanned": self.files_scanned,
            "files_excluded": self.files_excluded,
            "units_total": len(self.units),
            "by_kind": by_kind,
            "by_role": by_role,
            "by_language": by_language,
        }

    def validate(self) -> None:
        for u in self.units:
            u.validate()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "target_root": self.target_root,
            "generated_at": self.generated_at or datetime.now(timezone.utc).isoformat(),
            "detected_frameworks": self.detected_frameworks,
            "warnings": self.warnings,
            "stats": self.compute_stats(),
            "units": [u.to_dict() for u in self.units],
        }


class IdFactory:
    """Stable, sequential SRC-NNNN id generator (matches v0.1.0 id format)."""

    def __init__(self) -> None:
        self._n = 0

    def __call__(self) -> str:
        self._n += 1
        return f"SRC-{self._n:04d}"

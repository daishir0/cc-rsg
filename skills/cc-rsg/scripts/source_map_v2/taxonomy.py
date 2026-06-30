"""cc-rsg source-map v2 — the role taxonomy ("constitution").

This module is the single source of truth for the *language-neutral* vocabulary
that every per-language extractor must map its findings onto. It is anchored to
the "5 universal tables" already used by `references/outline-tables.md`
(Modules / Entities / Actions / Data / Dependencies) so that the mechanical
source map, the LLM-built inventory, and the outline tables all speak the same
language.

Design rule (P1 in the v2 design doc): no per-language vocabulary may leak.
A `kind` (e.g. ``"fastapi_endpoint"``) is language/framework specific, but every
`kind` MUST resolve to exactly one ``role`` defined here, and every ``role`` to
exactly one of the five universal tables.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# The 5 universal tables (outline-tables.md "5 universal tables")
# ---------------------------------------------------------------------------

TABLE_MODULES = "Modules"
TABLE_ENTITIES = "Entities"
TABLE_ACTIONS = "Actions"
TABLE_DATA = "Data"
TABLE_DEPENDENCIES = "Dependencies"

UNIVERSAL_TABLES = (
    TABLE_MODULES,
    TABLE_ENTITIES,
    TABLE_ACTIONS,
    TABLE_DATA,
    TABLE_DEPENDENCIES,
)

# ---------------------------------------------------------------------------
# Roles (the common vocabulary) -> universal table
# ---------------------------------------------------------------------------

ROLE_TABLE: dict[str, str] = {
    # Modules
    "module": TABLE_MODULES,        # namespace / package / COBOL PROGRAM-ID
    "class": TABLE_MODULES,         # class / trait / struct / record
    # Entities
    "model": TABLE_ENTITIES,        # persisted entity (ORM model)
    "schema": TABLE_ENTITIES,       # DTO / data type / validation (Pydantic, TS interface/type/enum, Zod)
    "component": TABLE_ENTITIES,    # UI / view unit (React/Vue component, template, page, screen)
    # Actions
    "endpoint": TABLE_ACTIONS,      # external I/F (HTTP/WS/GraphQL) — carries method + path
    "route_group": TABLE_ACTIONS,   # a grouping of routes (Rails resources, Flask Blueprint)
    "callable": TABLE_ACTIONS,      # function / method / procedure (not an endpoint)
    "command": TABLE_ACTIONS,       # CLI / task entrypoint (Artisan, Click, rake)
    "job": TABLE_ACTIONS,           # async / background worker (Celery, Sidekiq, BullMQ)
    # Data
    "datastore": TABLE_DATA,        # individual DB object (table/view/proc/trigger/index/FK)
    "migration": TABLE_DATA,        # schema-change unit
    # Dependencies
    "dependency": TABLE_DEPENDENCIES,  # DI provider / middleware / hook / exception handler
    "config": TABLE_DEPENDENCIES,      # config file / key
}

ROLES = tuple(ROLE_TABLE.keys())

# Tiers are orthogonal to role (matches inventory-units.md macro/middle/micro).
TIERS = ("macro", "middle", "micro")

# ---------------------------------------------------------------------------
# kind -> (role, default tier) registry.
# Per-language extractors register their kinds here at import time so that role
# typing stays centralised and auditable. M0 ships an empty registry; M2+ fill
# it. The registry is the contract every extractor is checked against.
# ---------------------------------------------------------------------------

_KIND_REGISTRY: dict[str, tuple[str, str]] = {}


class TaxonomyError(ValueError):
    """Raised when a kind/role/tier violates the constitution."""


def register_kind(kind: str, role: str, tier: str = "middle") -> None:
    """Register a language-specific ``kind`` and bind it to a common ``role``.

    Raises TaxonomyError if the role/tier are not part of the constitution or if
    the same kind is re-registered with a conflicting role (catches drift early).
    """
    if role not in ROLE_TABLE:
        raise TaxonomyError(f"unknown role {role!r} for kind {kind!r}; valid roles: {sorted(ROLES)}")
    if tier not in TIERS:
        raise TaxonomyError(f"unknown tier {tier!r} for kind {kind!r}; valid tiers: {TIERS}")
    existing = _KIND_REGISTRY.get(kind)
    if existing is not None and existing[0] != role:
        raise TaxonomyError(
            f"kind {kind!r} already registered as role {existing[0]!r}, refused to rebind to {role!r}"
        )
    _KIND_REGISTRY[kind] = (role, tier)


def role_for_kind(kind: str) -> str | None:
    entry = _KIND_REGISTRY.get(kind)
    return entry[0] if entry else None


def tier_for_kind(kind: str) -> str | None:
    entry = _KIND_REGISTRY.get(kind)
    return entry[1] if entry else None


def table_for_role(role: str) -> str:
    try:
        return ROLE_TABLE[role]
    except KeyError:
        raise TaxonomyError(f"unknown role {role!r}; valid roles: {sorted(ROLES)}")


def is_valid_role(role: str) -> bool:
    return role in ROLE_TABLE


def registered_kinds() -> dict[str, tuple[str, str]]:
    """Return a copy of the current kind registry (for audits / tests)."""
    return dict(_KIND_REGISTRY)

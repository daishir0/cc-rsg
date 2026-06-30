"""M6 — SQL extractor (regex based; dialect-robust).

Parses DDL into per-object datastore units: tables, views, stored
procedures/functions, triggers, indexes. Regex is used deliberately (no
tree-sitter SQL dialect dependency), matching the grep-based approach in
references/inventory-units.md.
"""

from __future__ import annotations

import re
from typing import Callable

from .. import taxonomy
from ..model import SourceUnit, fingerprint
from . import register, Extractor

for _kind in ("sql_table", "sql_view", "sql_routine", "sql_trigger", "sql_index"):
    taxonomy.register_kind(_kind, "datastore", "middle")

_ID = r'["`\[]?([A-Za-z_][\w.]*)["`\]]?'
_PATTERNS = [
    ("sql_table", re.compile(r"\bCREATE\s+(?:TEMP(?:ORARY)?\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?" + _ID, re.I)),
    ("sql_view", re.compile(r"\bCREATE\s+(?:OR\s+REPLACE\s+)?(?:MATERIALIZED\s+)?VIEW\s+" + _ID, re.I)),
    ("sql_routine", re.compile(r"\bCREATE\s+(?:OR\s+REPLACE\s+)?(?:FUNCTION|PROCEDURE)\s+" + _ID, re.I)),
    ("sql_trigger", re.compile(r"\bCREATE\s+(?:OR\s+REPLACE\s+)?TRIGGER\s+" + _ID, re.I)),
    ("sql_index", re.compile(r"\bCREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?" + _ID, re.I)),
]


class SqlExtractor(Extractor):
    language = "sql"

    def extract(self, path, source, id_factory: Callable[[], str], framework=None, context=None):
        out: list[SourceUnit] = []
        for kind, pat in _PATTERNS:
            for m in pat.finditer(source):
                line = source.count("\n", 0, m.start()) + 1
                name = m.group(1)
                out.append(SourceUnit(
                    id=id_factory(), path=path, line_range=(line, line), language="sql",
                    role="datastore", kind=kind, name=name, framework=framework,
                    signature=m.group(0).strip()[:200],
                    fingerprint=fingerprint(m.group(0)),
                ))
        out.sort(key=lambda u: u.line_range[0])
        return out


register(SqlExtractor())

"""M6 — COBOL extractor (regex based; fixed/free format).

PROGRAM-ID (module), SECTION / PARAGRAPH (callable), CALL targets (dependency),
SELECT / FD file definitions (datastore). Regex matches the grep-based approach
in references/inventory-units.md; tree-sitter COBOL grammars are unreliable.
"""

from __future__ import annotations

import re
from typing import Callable

from .. import taxonomy
from ..model import SourceUnit, fingerprint
from . import register, Extractor

taxonomy.register_kind("cobol_program", "module", "macro")
taxonomy.register_kind("cobol_section", "callable", "middle")
taxonomy.register_kind("cobol_paragraph", "callable", "micro")
taxonomy.register_kind("cobol_call", "dependency", "middle")
taxonomy.register_kind("cobol_data", "datastore", "middle")

_NAME = r"([A-Za-z0-9][A-Za-z0-9-]*)"
_PROGRAM = re.compile(r"\bPROGRAM-ID\s*\.\s*" + _NAME, re.I)
_SECTION = re.compile(r"^\s*" + _NAME + r"\s+SECTION\s*\.", re.I | re.M)
_PARAGRAPH = re.compile(r"^[ ]{0,7}" + _NAME + r"\s*\.\s*$", re.M)
_CALL = re.compile(r"\bCALL\s+[\"']?" + _NAME, re.I)
_SELECT = re.compile(r"\bSELECT\s+" + _NAME, re.I)
_FD = re.compile(r"^\s*FD\s+" + _NAME, re.I | re.M)

# Words that look like paragraphs but are division/section keywords to skip.
_KEYWORDS = {"IDENTIFICATION", "ENVIRONMENT", "DATA", "PROCEDURE", "DIVISION",
             "WORKING-STORAGE", "FILE", "LINKAGE", "CONFIGURATION", "INPUT-OUTPUT"}


class CobolExtractor(Extractor):
    language = "cobol"

    def extract(self, path, source, id_factory: Callable[[], str], framework=None, context=None):
        out: list[SourceUnit] = []
        section_names = {m.group(1).upper() for m in _SECTION.finditer(source)}

        def add(kind, role, name, start, sig):
            line = source.count("\n", 0, start) + 1
            out.append(SourceUnit(
                id=id_factory(), path=path, line_range=(line, line), language="cobol",
                role=role, kind=kind, name=name, framework=framework,
                signature=sig.strip()[:200], fingerprint=fingerprint(sig),
            ))

        for m in _PROGRAM.finditer(source):
            add("cobol_program", "module", m.group(1), m.start(), m.group(0))
        for m in _SECTION.finditer(source):
            add("cobol_section", "callable", m.group(1), m.start(), m.group(0))
        for m in _PARAGRAPH.finditer(source):
            name = m.group(1)
            up = name.upper()
            if up in _KEYWORDS or up in section_names or "-" not in name and name.isdigit():
                continue
            add("cobol_paragraph", "callable", name, m.start(), m.group(0))
        for m in _CALL.finditer(source):
            add("cobol_call", "dependency", m.group(1), m.start(), m.group(0))
        for m in _SELECT.finditer(source):
            add("cobol_data", "datastore", m.group(1), m.start(), m.group(0))
        for m in _FD.finditer(source):
            add("cobol_data", "datastore", m.group(1), m.start(), m.group(0))

        out.sort(key=lambda u: u.line_range[0])
        return out


register(CobolExtractor())

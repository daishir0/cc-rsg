"""M5 — Java extractor (tree-sitter based, Spring-aware).

Classes / interfaces / enums / records, Spring stereotypes
(@RestController/@Service/@Repository/@Component → role typing, @Entity → model),
and @*Mapping endpoints (method + path).
"""

from __future__ import annotations

from typing import Callable

from .. import taxonomy
from ..model import SourceUnit, fingerprint
from . import register, Extractor
from . import tshelpers as H

for _kind, _role, _tier in [
    ("java_class", "class", "middle"),
    ("java_interface", "schema", "middle"),
    ("java_enum", "schema", "middle"),
    ("java_record", "schema", "middle"),
    ("spring_controller", "class", "middle"),
    ("spring_service", "dependency", "middle"),
    ("jpa_entity", "model", "middle"),
    ("spring_endpoint", "endpoint", "middle"),
]:
    taxonomy.register_kind(_kind, _role, _tier)

_MAPPING_METHOD = {
    "GetMapping": "GET", "PostMapping": "POST", "PutMapping": "PUT",
    "PatchMapping": "PATCH", "DeleteMapping": "DELETE", "RequestMapping": "ANY",
}


def _annotations(node, src) -> list[str]:
    mods = H.field(node, "modifiers") or next((c for c in node.children if c.type == "modifiers"), None)
    out = []
    if mods:
        for c in mods.children:
            if c.type in ("marker_annotation", "annotation"):
                nm = H.field(c, "name")
                if nm:
                    out.append(H.text(nm, src))
    return out


def _annotation_arg(node, src) -> str | None:
    mods = H.field(node, "modifiers") or next((c for c in node.children if c.type == "modifiers"), None)
    if not mods:
        return None
    for c in mods.children:
        if c.type == "annotation":
            for s in _descend(c):
                if s.type == "string_literal":
                    return H.text(s, src).strip("\"'")
    return None


def _descend(node):
    yield node
    for c in node.children:
        yield from _descend(c)


class JavaExtractor(Extractor):
    language = "java"

    def extract(self, path, source, id_factory: Callable[[], str], framework=None, context=None):
        tree, src = H.parse("java", source)
        out: list[SourceUnit] = []

        def emit(role, kind, name, node, endpoint=None):
            s, e = H.line_range(node)
            out.append(SourceUnit(
                id=id_factory(), path=path, line_range=(s, e), language="java",
                role=role, kind=kind, name=name, framework=framework,
                signature=H.text(node, src).splitlines()[0].strip()[:200],
                endpoint=endpoint, fingerprint=fingerprint(H.text(node, src)),
            ))

        def handle_class(c):
            anns = set(_annotations(c, src))
            name = H.name_of(c, src)
            if anns & {"RestController", "Controller"}:
                emit("class", "spring_controller", name, c)
                _emit_endpoints(c, name)
            elif "Entity" in anns:
                emit("model", "jpa_entity", name, c)
            elif anns & {"Service", "Repository", "Component"}:
                emit("dependency", "spring_service", name, c)
            else:
                emit("class", "java_class", name, c)

        def _emit_endpoints(class_node, ctrl):
            body = H.field(class_node, "body") or next(
                (x for x in class_node.children if x.type == "class_body"), None)
            if not body:
                return
            for m in body.children:
                if m.type != "method_declaration":
                    continue
                for ann in _annotations(m, src):
                    if ann in _MAPPING_METHOD:
                        method = _MAPPING_METHOD[ann]
                        p = _annotation_arg(m, src) or ""
                        emit("endpoint", "spring_endpoint",
                             f"{ctrl}#{H.name_of(m, src)}", m,
                             endpoint={"method": method, "path": p})
                        break

        def walk(node):
            for c in node.children:
                if c.type == "class_declaration":
                    handle_class(c)
                elif c.type == "interface_declaration":
                    emit("schema", "java_interface", H.name_of(c, src), c)
                elif c.type == "enum_declaration":
                    emit("schema", "java_enum", H.name_of(c, src), c)
                elif c.type == "record_declaration":
                    emit("schema", "java_record", H.name_of(c, src), c)

        walk(tree.root_node)
        return out


if H.have("java"):
    register(JavaExtractor())

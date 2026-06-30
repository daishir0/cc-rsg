"""M5 — C# extractor (tree-sitter based, ASP.NET Core-aware).

Classes / interfaces / records / structs, controller actions decorated with
[HttpGet]/[HttpPost]/... (method + path), and Minimal API app.MapGet("/x", ...).
"""

from __future__ import annotations

from typing import Callable

from .. import taxonomy
from ..model import SourceUnit, fingerprint
from . import register, Extractor
from . import tshelpers as H

for _kind, _role, _tier in [
    ("csharp_class", "class", "middle"),
    ("csharp_interface", "schema", "middle"),
    ("csharp_record", "schema", "middle"),
    ("csharp_struct", "schema", "middle"),
    ("aspnet_endpoint", "endpoint", "middle"),
]:
    taxonomy.register_kind(_kind, _role, _tier)

_HTTP_ATTR = {
    "HttpGet": "GET", "HttpPost": "POST", "HttpPut": "PUT",
    "HttpPatch": "PATCH", "HttpDelete": "DELETE",
}
_MINIMAL_MAP = {
    "MapGet": "GET", "MapPost": "POST", "MapPut": "PUT",
    "MapPatch": "PATCH", "MapDelete": "DELETE",
}


def _descend(node):
    yield node
    for c in node.children:
        yield from _descend(c)


def _attr_names_and_arg(node, src):
    """Return (set of attribute names, first string literal inside any attribute)."""
    names, arg = set(), None
    for c in node.children:
        if c.type == "attribute_list":
            for a in _descend(c):
                if a.type == "attribute":
                    nm = H.field(a, "name")
                    if nm:
                        names.add(H.text(nm, src))
                if a.type == "string_literal" and arg is None:
                    arg = H.text(a, src).strip("\"'@")
    return names, arg


class CSharpExtractor(Extractor):
    language = "csharp"

    def extract(self, path, source, id_factory: Callable[[], str], framework=None, context=None):
        tree, src = H.parse("csharp", source)
        out: list[SourceUnit] = []

        def emit(role, kind, name, node, endpoint=None):
            s, e = H.line_range(node)
            out.append(SourceUnit(
                id=id_factory(), path=path, line_range=(s, e), language="csharp",
                role=role, kind=kind, name=name, framework=framework,
                signature=H.text(node, src).splitlines()[0].strip()[:200],
                endpoint=endpoint, fingerprint=fingerprint(H.text(node, src)),
            ))

        def _emit_actions(class_node, cname):
            body = next((c for c in class_node.children if c.type == "declaration_list"), None)
            if not body:
                return
            for m in body.children:
                if m.type != "method_declaration":
                    continue
                names, arg = _attr_names_and_arg(m, src)
                for attr in names:
                    if attr in _HTTP_ATTR:
                        emit("endpoint", "aspnet_endpoint", f"{cname}#{H.name_of(m, src)}", m,
                             endpoint={"method": _HTTP_ATTR[attr], "path": arg or ""})
                        break

        def walk(node):
            for c in node.children:
                if c.type == "class_declaration":
                    name = H.name_of(c, src)
                    emit("class", "csharp_class", name, c)
                    _emit_actions(c, name)
                elif c.type == "interface_declaration":
                    emit("schema", "csharp_interface", H.name_of(c, src), c)
                elif c.type == "record_declaration":
                    emit("schema", "csharp_record", H.name_of(c, src), c)
                elif c.type == "struct_declaration":
                    emit("schema", "csharp_struct", H.name_of(c, src), c)
                elif c.type in ("namespace_declaration", "file_scoped_namespace_declaration"):
                    walk(c)
                elif c.type in ("global_statement", "expression_statement"):
                    _maybe_minimal_api(c)

        def _maybe_minimal_api(stmt):
            for d in _descend(stmt):
                if d.type == "invocation_expression":
                    fn = H.field(d, "function")
                    if fn is not None and fn.type == "member_access_expression":
                        nm = H.field(fn, "name")
                        verb = H.text(nm, src) if nm else ""
                        if verb in _MINIMAL_MAP:
                            p = H.first_string_arg(d, src)
                            if p:
                                emit("endpoint", "aspnet_endpoint", f"{_MINIMAL_MAP[verb]} {p}", stmt,
                                     endpoint={"method": _MINIMAL_MAP[verb], "path": p})
                            return

        walk(tree.root_node)
        return out


if H.have("csharp"):
    register(CSharpExtractor())

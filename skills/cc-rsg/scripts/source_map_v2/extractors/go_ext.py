"""M6 — Go extractor (tree-sitter based).

Structs / interfaces / type aliases (schema), functions & methods (callable),
and HTTP handlers (http.HandleFunc / gin / echo / chi router .GET("/x", ...)).
"""

from __future__ import annotations

from typing import Callable

from .. import taxonomy
from ..model import SourceUnit, fingerprint
from . import register, Extractor
from . import tshelpers as H

for _kind, _role, _tier in [
    ("go_struct", "schema", "middle"),
    ("go_interface", "schema", "middle"),
    ("go_type", "schema", "middle"),
    ("go_func", "callable", "middle"),
    ("go_method", "callable", "middle"),
    ("go_endpoint", "endpoint", "middle"),
]:
    taxonomy.register_kind(_kind, _role, _tier)

_HTTP = {"get", "post", "put", "patch", "delete", "handle", "handlefunc"}


class GoExtractor(Extractor):
    language = "go"

    def extract(self, path, source, id_factory: Callable[[], str], framework=None, context=None):
        tree, src = H.parse("go", source)
        out: list[SourceUnit] = []

        def emit(role, kind, name, node, endpoint=None):
            s, e = H.line_range(node)
            out.append(SourceUnit(
                id=id_factory(), path=path, line_range=(s, e), language="go",
                role=role, kind=kind, name=name, framework=framework,
                signature=H.text(node, src).splitlines()[0].strip()[:200],
                endpoint=endpoint, fingerprint=fingerprint(H.text(node, src)),
            ))

        def handle_type_decl(node):
            for spec in node.children:
                if spec.type == "type_spec":
                    nm = H.field(spec, "name")
                    ty = H.field(spec, "type")
                    name = H.text(nm, src) if nm else "?"
                    if ty is not None and ty.type == "struct_type":
                        emit("schema", "go_struct", name, spec)
                    elif ty is not None and ty.type == "interface_type":
                        emit("schema", "go_interface", name, spec)
                    else:
                        emit("schema", "go_type", name, spec)

        for c in tree.root_node.children:
            if c.type == "type_declaration":
                handle_type_decl(c)
            elif c.type == "function_declaration":
                nm = H.field(c, "name")
                emit("callable", "go_func", H.text(nm, src) if nm else "?", c)
            elif c.type == "method_declaration":
                nm = H.field(c, "name")
                emit("callable", "go_method", H.text(nm, src) if nm else "?", c)

        # HTTP handlers anywhere in the tree.
        def scan(node):
            if node.type == "call_expression":
                fn = H.field(node, "function")
                if fn is not None and fn.type == "selector_expression":
                    field_n = H.field(fn, "field")
                    verb = H.text(field_n, src).lower() if field_n else ""
                    if verb in _HTTP:
                        p = H.first_string_arg(node, src)
                        if p and p.startswith("/"):
                            method = "ANY" if verb in ("handle", "handlefunc") else verb.upper()
                            s, e = H.line_range(node)
                            out.append(SourceUnit(
                                id=id_factory(), path=path, line_range=(s, e), language="go",
                                role="endpoint", kind="go_endpoint", name=f"{method} {p}",
                                framework=framework, endpoint={"method": method, "path": p},
                                signature=H.text(node, src).splitlines()[0].strip()[:200],
                                fingerprint=fingerprint(H.text(node, src)),
                            ))
            for ch in node.children:
                scan(ch)

        scan(tree.root_node)
        return out


if H.have("go"):
    register(GoExtractor())

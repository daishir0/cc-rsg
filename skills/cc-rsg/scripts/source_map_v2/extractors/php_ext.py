"""M5 — PHP extractor (tree-sitter based).

Classes / interfaces / traits / top-level functions, Laravel ``Route::verb``
endpoints, and Eloquent models (``extends Model``).
"""

from __future__ import annotations

from typing import Callable

from .. import taxonomy
from ..model import SourceUnit, fingerprint
from . import register, Extractor
from . import tshelpers as H

for _kind, _role, _tier in [
    ("php_class", "class", "middle"),
    ("php_interface", "schema", "middle"),
    ("php_trait", "class", "middle"),
    ("php_function", "callable", "middle"),
    ("laravel_route", "endpoint", "middle"),
    ("eloquent_model", "model", "middle"),
]:
    taxonomy.register_kind(_kind, _role, _tier)

_HTTP = {"get", "post", "put", "patch", "delete", "options", "any", "match"}


class PhpExtractor(Extractor):
    language = "php"

    def extract(self, path, source, id_factory: Callable[[], str], framework=None, context=None):
        tree, src = H.parse("php", source)
        out: list[SourceUnit] = []

        def emit(role, kind, name, node, endpoint=None):
            s, e = H.line_range(node)
            out.append(SourceUnit(
                id=id_factory(), path=path, line_range=(s, e), language="php",
                role=role, kind=kind, name=name, framework=framework,
                signature=H.text(node, src).splitlines()[0].strip()[:200],
                endpoint=endpoint, fingerprint=fingerprint(H.text(node, src)),
            ))

        def walk(node):
            for c in node.children:
                if c.type == "class_declaration":
                    blob = H.text(c, src)[:200]
                    if "extends Model" in blob or "extends Authenticatable" in blob:
                        emit("model", "eloquent_model", H.name_of(c, src), c)
                    else:
                        emit("class", "php_class", H.name_of(c, src), c)
                elif c.type == "interface_declaration":
                    emit("schema", "php_interface", H.name_of(c, src), c)
                elif c.type == "trait_declaration":
                    emit("class", "php_trait", H.name_of(c, src), c)
                elif c.type == "function_definition":
                    emit("callable", "php_function", H.name_of(c, src), c)
                elif c.type == "expression_statement":
                    _maybe_route(c)
                # descend into namespaces / blocks
                if c.type in ("namespace_definition", "compound_statement", "declaration_list", "program"):
                    walk(c)

        def _maybe_route(stmt):
            # Route::get('/path', ...)
            blob = H.text(stmt, src)
            sce = None
            for d in _descend(stmt):
                if d.type == "scoped_call_expression":
                    sce = d
                    break
            if sce is None:
                return
            scope = H.field(sce, "scope")
            nm = H.field(sce, "name")
            if scope is None or nm is None:
                return
            if H.text(scope, src) != "Route":
                return
            verb = H.text(nm, src).lower()
            if verb not in _HTTP:
                return
            p = H.first_string_arg(sce, src)
            if p:
                method = "ANY" if verb in ("any", "match") else verb.upper()
                emit("endpoint", "laravel_route", f"{method} {p}", stmt,
                     endpoint={"method": method, "path": p})

        def _descend(node):
            yield node
            for c in node.children:
                yield from _descend(c)

        walk(tree.root_node)
        return out


if H.have("php"):
    register(PhpExtractor())

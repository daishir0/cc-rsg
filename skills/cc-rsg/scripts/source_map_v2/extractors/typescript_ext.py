"""M2 — TypeScript/JavaScript extractor (tree-sitter based, framework-aware).

Recovers what the v1 regex got wrong:
  - interface / type / enum with their REAL names (v1 captured the keyword)
  - class declarations with real block ranges (v1 emitted single-line)
  - non-exported functions / const arrows (v1 dropped them)
  - Express/Fastify/Hono routes (app.get("/x", ...)) as endpoint + method/path
  - NestJS @Controller/@Injectable/@Module role typing
  - React components (Capitalized arrow/function) as role=component
"""

from __future__ import annotations

from typing import Callable

from .. import taxonomy
from ..model import SourceUnit, fingerprint
from . import register, Extractor
from . import tshelpers as H

for _kind, _role, _tier in [
    ("ts_class", "class", "middle"),
    ("ts_interface", "schema", "middle"),
    ("ts_type", "schema", "middle"),
    ("ts_enum", "schema", "middle"),
    ("ts_function", "callable", "middle"),
    ("ts_const", "callable", "middle"),
    ("react_component", "component", "middle"),
    ("express_route", "endpoint", "middle"),
    ("nest_controller", "class", "middle"),
    ("nest_service", "class", "middle"),
    ("nest_module", "module", "middle"),
]:
    taxonomy.register_kind(_kind, _role, _tier)

_NAMED_DECL = {
    "interface_declaration": ("schema", "ts_interface"),
    "type_alias_declaration": ("schema", "ts_type"),
    "enum_declaration": ("schema", "ts_enum"),
    "class_declaration": ("class", "ts_class"),
    "function_declaration": ("callable", "ts_function"),
}

_HTTP_VERBS = {"get", "post", "put", "patch", "delete", "head", "options", "all", "use", "ws"}


def _class_kind_from_decorators(node, src):
    """NestJS role typing from class decorators (@Controller/@Injectable/@Module)."""
    for c in node.children:
        if c.type == "decorator":
            t = H.text(c, src)
            if "@Controller" in t:
                return "class", "nest_controller"
            if "@Injectable" in t:
                return "class", "nest_service"
            if "@Module" in t:
                return "module", "nest_module"
    return None


class TypeScriptExtractor(Extractor):
    language = "typescript"

    def extract(self, path, source, id_factory: Callable[[], str], framework=None, context=None):
        # .tsx files use the tsx grammar (JSX), else the typescript grammar.
        lang = "tsx" if path.endswith(".tsx") else "typescript"
        if not H.have(lang):
            lang = "typescript"
        tree, src = H.parse(lang, source)
        out: list[SourceUnit] = []
        is_tsx = path.endswith((".tsx", ".jsx"))

        def emit(role, kind, name, node, exported, tier="middle", endpoint=None):
            s, e = H.line_range(node)
            sig = H.text(node, src).splitlines()[0].strip() if H.text(node, src) else name
            out.append(SourceUnit(
                id=id_factory(), path=path, line_range=(s, e), language="typescript",
                role=role, kind=kind, tier=tier, name=name, framework=framework,
                signature=(("export " if exported else "") + sig)[:200],
                endpoint=endpoint, fingerprint=fingerprint(H.text(node, src)),
            ))

        def handle_named(node, exported):
            if node.type in _NAMED_DECL:
                role, kind = _NAMED_DECL[node.type]
                if node.type == "class_declaration":
                    nest = _class_kind_from_decorators(node, src)
                    if nest:
                        role, kind = nest
                nm = H.field(node, "name")
                emit(role, kind, H.text(nm, src) if nm else "?", node, exported)
                return True
            if node.type == "lexical_declaration":  # const/let x = ...
                for d in node.children:
                    if d.type == "variable_declarator":
                        nm = H.field(d, "name")
                        name = H.text(nm, src) if nm else "?"
                        val = H.field(d, "value")
                        is_arrow = val is not None and val.type == "arrow_function"
                        if is_tsx and name[:1].isupper() and is_arrow:
                            emit("component", "react_component", name, node, exported)
                        elif is_arrow:
                            emit("callable", "ts_const", name, node, exported)
                return True
            return False

        # top-level declarations (exported or not)
        for c in tree.root_node.children:
            if c.type == "export_statement":
                inner = c.children[-1]
                handle_named(inner, exported=True)
            else:
                handle_named(c, exported=False)

        # Express/Fastify/Hono routes: scan all call_expressions for
        #   x.verb("/path", handler)
        # Require an actual handler argument so client-side calls like
        # axios.get("/api/x") (no callback) are not mistaken for route defs, and
        # skip entirely on view frameworks (React/Vue) where there are no routes.
        _HANDLER_TYPES = {"arrow_function", "function", "function_expression",
                          "identifier", "member_expression"}

        def _has_handler(call_node):
            args = H.field(call_node, "arguments")
            if not args:
                return False
            real = [a for a in args.children if a.type not in ("(", ")", ",")]
            # need at least [path, handler] and a handler-typed arg after the path
            return len(real) >= 2 and any(a.type in _HANDLER_TYPES for a in real[1:])

        scan_routes_enabled = framework not in ("react", "vue")

        def scan_routes(node):
            if node.type == "call_expression":
                fn = H.field(node, "function")
                if fn is not None and fn.type == "member_expression":
                    prop = H.field(fn, "property")
                    verb = H.text(prop, src).lower() if prop else ""
                    if verb in _HTTP_VERBS and verb not in ("use", "all") and _has_handler(node):
                        p = H.first_string_arg(node, src)
                        if p and p.startswith("/"):
                            s, e = H.line_range(node)
                            out.append(SourceUnit(
                                id=id_factory(), path=path, line_range=(s, e),
                                language="typescript", role="endpoint", kind="express_route",
                                tier="middle", name=f"{verb.upper()} {p}", framework=framework,
                                signature=H.text(node, src).splitlines()[0].strip()[:200],
                                endpoint={"method": verb.upper(), "path": p},
                                fingerprint=fingerprint(H.text(node, src)),
                            ))
            for ch in node.children:
                scan_routes(ch)

        if scan_routes_enabled:
            scan_routes(tree.root_node)
        return out


if H.have("typescript"):
    register(TypeScriptExtractor())
    # JS uses the same extractor (the typescript grammar parses plain JS too).
    js = TypeScriptExtractor()
    js.language = "javascript"
    register(js)

"""M4 — Ruby / Rails extractor (tree-sitter based).

Upgrades the v1 behaviour (every class -> undifferentiated ``ruby_class``) to the
Rails 14-unit catalogue, role-typed by file path (the catalogue is path-driven):
controllers / models / concerns / services / jobs / mailers / helpers / lib,
plus controller actions (endpoints), route groups (config/routes.rb) and
migrations (db/migrate).
"""

from __future__ import annotations

from typing import Callable

from .. import taxonomy
from ..model import SourceUnit, fingerprint
from . import register, Extractor
from . import tshelpers as H

for _kind, _role, _tier in [
    ("ruby_class", "class", "middle"),
    ("ruby_module", "module", "middle"),
    ("ruby_function", "callable", "middle"),
    ("rails_controller", "class", "middle"),
    ("rails_action", "endpoint", "middle"),
    ("rails_model", "model", "middle"),
    ("rails_concern", "class", "middle"),
    ("rails_service", "class", "middle"),
    ("rails_job", "job", "middle"),
    ("rails_mailer", "class", "middle"),
    ("rails_helper", "class", "middle"),
    ("rails_lib", "class", "middle"),
    ("rails_route", "route_group", "middle"),
    ("rails_migration", "migration", "middle"),
]:
    taxonomy.register_kind(_kind, _role, _tier)

# Route-DSL methods that define a *group* of routes vs a single route.
# Note: `draw` is the routes.rb wrapper block, not a route group — excluded.
_ROUTE_GROUP_DSL = {"resources", "resource", "namespace", "scope"}
_ROUTE_SINGLE_DSL = {"get", "post", "put", "patch", "delete", "root", "match"}


def _rails_class_kind(path: str):
    """Map a file path to (kind, role) per the Rails 14-unit catalogue, or None."""
    # Normalise to a leading-slash form so "app/models/x.rb" and
    # "/repo/app/models/x.rb" both match the "/app/models/" markers.
    p = "/" + path.replace("\\", "/").lstrip("/")
    if "/app/controllers/concerns/" in p or "/app/models/concerns/" in p:
        return ("rails_concern", "class")
    if "/db/migrate/" in p:
        return ("rails_migration", "migration")
    if "/app/controllers/" in p:
        return ("rails_controller", "class")
    if "/app/models/" in p:
        return ("rails_model", "model")
    if "/app/services/" in p or "/app/use_cases/" in p or "/lib/services/" in p:
        return ("rails_service", "class")
    if "/app/jobs/" in p:
        return ("rails_job", "job")
    if "/app/mailers/" in p:
        return ("rails_mailer", "class")
    if "/app/helpers/" in p:
        return ("rails_helper", "class")
    if "/lib/" in p:
        return ("rails_lib", "class")
    return None


def _name_text(node, src) -> str:
    nm = H.field(node, "name")
    return H.text(nm, src) if nm else "?"


def _call_name(node, src) -> str | None:
    """Callee name of a `call`/`command`/`method_call` node."""
    m = H.field(node, "method")
    if m is not None:
        return H.text(m, src)
    for c in node.children:
        if c.type == "identifier":
            return H.text(c, src)
    return None


def _first_arg_literal(node, src) -> str | None:
    args = H.field(node, "arguments")
    if args is None:
        for c in node.children:
            if c.type == "argument_list":
                args = c
                break
    if args is None:
        return None
    for a in args.children:
        if a.type in ("simple_symbol", "string", "string_content"):
            return H.text(a, src).lstrip(":").strip("\"'")
    return None


class RubyExtractor(Extractor):
    language = "ruby"

    def extract(self, path, source, id_factory: Callable[[], str], framework=None, context=None):
        tree, src = H.parse("ruby", source)
        out: list[SourceUnit] = []
        is_routes = path.replace("\\", "/").endswith("config/routes.rb")
        class_kind = _rails_class_kind(path)

        def emit(role, kind, name, node, tier="middle", endpoint=None):
            s, e = H.line_range(node)
            out.append(SourceUnit(
                id=id_factory(), path=path, line_range=(s, e), language="ruby",
                role=role, kind=kind, tier=tier, name=name, framework="rails" if class_kind else framework,
                signature=H.text(node, src).splitlines()[0].strip() if H.text(node, src) else name,
                endpoint=endpoint, fingerprint=fingerprint(H.text(node, src)),
            ))

        def visit(node, top_level):
            for c in node.children:
                if c.type == "class":
                    name = _name_text(c, src)
                    if class_kind:
                        kind, role = class_kind
                        emit(role, kind, name, c)
                        if kind == "rails_controller":
                            _emit_actions(c, name)
                    else:
                        emit("class", "ruby_class", name, c)
                    body = H.field(c, "body")
                    if body:
                        visit(body, top_level=False)
                elif c.type == "module":
                    name = _name_text(c, src)
                    if class_kind and class_kind[0] == "rails_concern":
                        emit("class", "rails_concern", name, c)
                    else:
                        emit("module", "ruby_module", name, c)
                    body = H.field(c, "body")
                    if body:
                        visit(body, top_level=False)
                elif c.type == "method" and top_level:
                    emit("callable", "ruby_function", _name_text(c, src), c)
                elif is_routes and c.type in ("call", "command", "method_call"):
                    _emit_route(c)
                    body = H.field(c, "block") or H.field(c, "body")
                    if body:
                        visit(body, top_level=False)
                else:
                    # descend into wrappers (do-blocks, begin, etc.) to find routes
                    if is_routes and c.child_count:
                        visit(c, top_level=False)

        def _emit_actions(class_node, ctrl_name):
            body = H.field(class_node, "body")
            if not body:
                return
            # Only PUBLIC instance methods are controller actions; methods after a
            # bare `private`/`protected` are before_action filters / helpers.
            public = True
            for c in body.children:
                if c.type == "identifier":
                    vis = H.text(c, src).strip()
                    if vis in ("private", "protected"):
                        public = False
                    elif vis == "public":
                        public = True
                    continue
                if c.type in ("call", "command"):
                    # `private :foo` / `private def ...` also flips visibility
                    if _call_name(c, src) in ("private", "protected"):
                        public = False
                    continue
                if c.type == "method" and public:
                    mname = _name_text(c, src)
                    emit("endpoint", "rails_action", f"{ctrl_name}#{mname}", c)

        def _emit_route(call_node):
            name = _call_name(call_node, src)
            if name in _ROUTE_GROUP_DSL:
                target = _first_arg_literal(call_node, src) or name
                emit("route_group", "rails_route", f"{name}:{target}", call_node)
            elif name in _ROUTE_SINGLE_DSL:
                path_lit = _first_arg_literal(call_node, src)
                method = name.upper() if name != "match" else "ANY"
                if name == "root":
                    method, path_lit = "GET", "/"
                emit("endpoint", "rails_action", f"{method} {path_lit or ''}".strip(), call_node,
                     endpoint={"method": method, "path": path_lit or "/"})

        visit(tree.root_node, top_level=True)
        return out


if H.have("ruby"):
    register(RubyExtractor())

"""M3 — Python extractor (tree-sitter based, framework-aware).

Recovers what the v1 regex dropped:
  - async def endpoints (FastAPI/Flask) with method + path role-typing
  - Pydantic schemas (BaseModel/RootModel subclasses) as role=schema
  - Django models as role=model
  - Celery tasks / FastAPI middleware / exception handlers as role=dependency/job
  - plain top-level functions (callable) and classes (class)
"""

from __future__ import annotations

import re
from typing import Callable

from .. import taxonomy
from ..model import SourceUnit, fingerprint
from . import register, Extractor
from . import tshelpers as H

# Register the kinds this extractor emits (binds each to a common role).
for _kind, _role, _tier in [
    ("py_class", "class", "middle"),
    ("py_function", "callable", "middle"),
    ("fastapi_endpoint", "endpoint", "middle"),
    ("flask_route", "endpoint", "middle"),
    ("http_endpoint", "endpoint", "middle"),
    ("pydantic_schema", "schema", "middle"),
    ("django_model", "model", "middle"),
    ("celery_task", "job", "middle"),
    ("fastapi_middleware", "dependency", "middle"),
    ("fastapi_exc_handler", "dependency", "middle"),
]:
    taxonomy.register_kind(_kind, _role, _tier)


def _decorator_route(dec_node, src):
    """If a decorator is an HTTP route, return (method, path); else None.

    Handles @app.get("/x"), @router.post("/y"), @app.websocket("/ws"),
    @bp.route("/z", methods=["POST"]).
    """
    call = None
    for c in dec_node.children:
        if c.type == "call":
            call = c
    if call is None:
        return None
    fn = H.field(call, "function")
    if fn is None or fn.type != "attribute":
        return None
    attr = H.field(fn, "attribute")
    if attr is None:
        return None
    verb = H.text(attr, src).lower()
    if verb not in H.HTTP_METHODS:
        return None
    path = H.first_string_arg(call, src)
    if verb == "route":
        method = "GET"
        # look for methods=[...] keyword
        args = H.field(call, "arguments")
        if args and "methods" in H.text(args, src):
            txt = H.text(args, src)
            for m in ("POST", "PUT", "PATCH", "DELETE", "GET"):
                if m in txt.upper():
                    method = m
                    break
        return (method, path)
    if verb == "websocket":
        return ("WEBSOCKET", path)
    return (verb.upper(), path)


def _endpoint_kind(framework: str | None) -> str:
    """Name the endpoint kind by detected framework; generic otherwise.

    Avoids mislabelling e.g. a Bottle ``@app.route`` as ``fastapi_endpoint``.
    """
    if framework == "fastapi":
        return "fastapi_endpoint"
    if framework == "flask":
        return "flask_route"
    return "http_endpoint"


def _decorator_kind(dec_node, src):
    """Non-route decorators that change role (task/middleware/exception handler)."""
    t = H.text(dec_node, src)
    if ".task" in t or "shared_task" in t:
        return "celery_task"
    if ".middleware(" in t or "add_middleware" in t:
        return "fastapi_middleware"
    if ".exception_handler(" in t:
        return "fastapi_exc_handler"
    return None


_CLASS_DEF_RE = re.compile(r"^\s*class\s+([A-Za-z_]\w*)\s*\(([^)]*)\)", re.MULTILINE)


def collect_pydantic_bases(sources: dict[str, str]) -> set[str]:
    """Cross-file resolution of Pydantic base classes (fixed-point).

    Seed = classes directly subclassing BaseModel/RootModel; then iterate: any
    class whose base list contains a known Pydantic base is itself Pydantic.
    Catches e.g. Mealie's ``MealieModel(BaseModel)`` and everything below it,
    which a single-file ``BaseModel`` check would miss.
    """
    edges: list[tuple[str, list[str]]] = []
    pyd: set[str] = {"BaseModel", "RootModel"}
    for text in sources.values():
        for m in _CLASS_DEF_RE.finditer(text):
            name = m.group(1)
            bases = [b.strip().split(".")[-1].split("[")[0].strip()
                     for b in m.group(2).split(",") if b.strip()]
            edges.append((name, bases))
            if any(b in pyd for b in bases):
                pyd.add(name)
    changed = True
    while changed:
        changed = False
        for name, bases in edges:
            if name not in pyd and any(b in pyd for b in bases):
                pyd.add(name)
                changed = True
    pyd.discard("BaseModel")
    pyd.discard("RootModel")
    return pyd


def _base_names(class_node, src) -> list[str]:
    sup = H.field(class_node, "superclasses")
    if not sup:
        return []
    raw = H.text(sup, src).strip("()")
    return [b.strip().split(".")[-1].split("[")[0].strip() for b in raw.split(",") if b.strip()]


def _class_role(class_node, src, framework, pydantic_bases: set[str]):
    bases = _base_names(class_node, src)
    base_blob = " ".join(bases)
    if "BaseModel" in base_blob or "RootModel" in base_blob or any(b in pydantic_bases for b in bases):
        return "schema", "pydantic_schema"
    if "Model" in base_blob and ("models" in (H.text(H.field(class_node, "superclasses"), src) if H.field(class_node, "superclasses") else "")):
        return "model", "django_model"
    if framework == "django" and "Model" in base_blob:
        return "model", "django_model"
    return "class", "py_class"


class PythonExtractor(Extractor):
    language = "python"

    def prescan(self, sources: dict[str, str]) -> dict:
        return {"pydantic_bases": collect_pydantic_bases(sources)}

    def extract(self, path, source, id_factory: Callable[[], str], framework=None, context=None):
        pydantic_bases = (context or {}).get("pydantic_bases", set())
        tree, src = H.parse("python", source)
        out: list[SourceUnit] = []

        def emit(role, kind, name, node, tier="middle", endpoint=None):
            s, e = H.line_range(node)
            out.append(SourceUnit(
                id=id_factory(), path=path, line_range=(s, e), language="python",
                role=role, kind=kind, tier=tier, name=name, framework=framework,
                signature=H.text(node, src).splitlines()[0].strip() if H.text(node, src) else name,
                endpoint=endpoint, fingerprint=fingerprint(H.text(node, src)),
            ))

        def handle_function(fn_node, decorators, module_level):
            name_n = H.field(fn_node, "name")
            name = H.text(name_n, src) if name_n else "?"
            routes = [r for r in (_decorator_route(d, src) for d in decorators) if r]
            if routes:
                method, p = routes[0]
                emit("endpoint", _endpoint_kind(framework), name, fn_node,
                     endpoint={"method": method, "path": p})
                return
            for d in decorators:
                k = _decorator_kind(d, src)
                if k:
                    role = taxonomy.role_for_kind(k) or "dependency"
                    emit(role, k, name, fn_node)
                    return
            if module_level:
                emit("callable", "py_function", name, fn_node)

        def visit(node, module_level):
            for c in node.children:
                if c.type == "decorated_definition":
                    decs = [d for d in c.children if d.type == "decorator"]
                    inner = c.children[-1]
                    if inner.type == "function_definition":
                        handle_function(inner, decs, module_level)
                    elif inner.type == "class_definition":
                        role, kind = _class_role(inner, src, framework, pydantic_bases)
                        nm = H.field(inner, "name")
                        emit(role, kind, H.text(nm, src) if nm else "?", inner)
                        body = H.field(inner, "body")
                        if body:
                            visit(body, module_level=False)  # nested endpoints (CBV controllers)
                elif c.type == "function_definition":
                    handle_function(c, [], module_level)
                elif c.type == "class_definition":
                    role, kind = _class_role(c, src, framework, pydantic_bases)
                    nm = H.field(c, "name")
                    emit(role, kind, H.text(nm, src) if nm else "?", c)
                    body = H.field(c, "body")
                    if body:
                        visit(body, module_level=False)

        visit(tree.root_node, module_level=True)
        return out


if H.have("python"):
    register(PythonExtractor())

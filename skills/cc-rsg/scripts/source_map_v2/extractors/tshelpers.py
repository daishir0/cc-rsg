"""tree-sitter helpers shared by the language extractors.

tree-sitter is an OPTIONAL dependency (design risk #1): if it (or a grammar) is
not installed, ``have(language)`` returns False and the language extractor does
not register, so the pipeline falls back to file-level units + a loud warning.
"""

from __future__ import annotations

from functools import lru_cache

try:
    import tree_sitter as _ts
    _HAVE_CORE = True
except ImportError:
    _HAVE_CORE = False


HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "websocket", "route"}


@lru_cache(maxsize=None)
def _parser(language: str):
    if not _HAVE_CORE:
        return None
    try:
        if language == "python":
            import tree_sitter_python as m
            lang = _ts.Language(m.language())
        elif language == "ruby":
            import tree_sitter_ruby as m
            lang = _ts.Language(m.language())
        elif language == "typescript":
            import tree_sitter_typescript as m
            lang = _ts.Language(m.language_typescript())
        elif language == "tsx":
            import tree_sitter_typescript as m
            lang = _ts.Language(m.language_tsx())
        elif language == "php":
            import tree_sitter_php as m
            lang = _ts.Language(m.language_php())
        elif language == "java":
            import tree_sitter_java as m
            lang = _ts.Language(m.language())
        elif language == "csharp":
            import tree_sitter_c_sharp as m
            lang = _ts.Language(m.language())
        elif language == "go":
            import tree_sitter_go as m
            lang = _ts.Language(m.language())
        else:
            return None
        return _ts.Parser(lang)
    except Exception:
        return None


def name_of(node, src: bytes) -> str:
    """Best-effort declaration name: the `name` field, else first identifier child."""
    nm = node.child_by_field_name("name")
    if nm is not None:
        return text(nm, src)
    for c in node.children:
        if c.type in ("identifier", "name", "type_identifier"):
            return text(c, src)
    return "?"


def have(language: str) -> bool:
    return _parser(language) is not None


def parse(language: str, source: str):
    p = _parser(language)
    if p is None:
        raise RuntimeError(f"tree-sitter parser for {language!r} unavailable")
    return p.parse(source.encode("utf-8", "replace")), source.encode("utf-8", "replace")


def text(node, src_bytes: bytes) -> str:
    return src_bytes[node.start_byte:node.end_byte].decode("utf-8", "replace")


def field(node, name: str):
    return node.child_by_field_name(name)


def line_range(node) -> tuple[int, int]:
    return (node.start_point[0] + 1, node.end_point[0] + 1)


_STRING_TYPES = {
    "string", "string_literal", "encapsed_string",
    "interpreted_string_literal", "raw_string_literal",
}
_STRING_CONTENT_TYPES = {"string_content", "string_fragment"}


def _string_value(node, src_bytes: bytes) -> str:
    for c in node.children:
        if c.type in _STRING_CONTENT_TYPES:
            return text(c, src_bytes)
    return text(node, src_bytes).strip("\"'`@")


def _first_string_descendant(node):
    for c in node.children:
        if c.type in _STRING_TYPES:
            return c
        found = _first_string_descendant(c)
        if found is not None:
            return found
    return None


def first_string_arg(call_node, src_bytes: bytes) -> str | None:
    """First string argument of a call, descending through arg wrappers.

    Handles both direct-string args (Python/TS: ``f("/x")``) and wrapped args
    (PHP: ``argument -> string -> string_content``).
    """
    args = field(call_node, "arguments")
    if not args:
        return None
    for a in args.children:
        if a.type in ("(", ")", ","):
            continue
        if a.type in _STRING_TYPES:
            return _string_value(a, src_bytes)
        found = _first_string_descendant(a)
        if found is not None:
            return _string_value(found, src_bytes)
    return None

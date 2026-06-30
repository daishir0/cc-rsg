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
        else:
            return None
        return _ts.Parser(lang)
    except Exception:
        return None


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


def first_string_arg(call_node, src_bytes: bytes) -> str | None:
    """Return the literal value of the first string argument of a call node."""
    args = field(call_node, "arguments")
    if not args:
        return None
    for a in args.children:
        if a.type in ("string", "string_literal"):
            return text(a, src_bytes).strip("\"'`")
    return None

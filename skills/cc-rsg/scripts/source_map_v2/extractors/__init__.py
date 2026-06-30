"""cc-rsg source-map v2 — layer 2: per-language extractor registry.

Each language gets one extractor (a subclass of ``Extractor``) registered here.
M0 ships an EMPTY registry: the three-layer skeleton runs end to end, but any
file whose language has no registered extractor falls back to a coarse
file-level unit and a loud warning (no silent exclusion — P4 in the design).

M2 adds TypeScript, M3 adds Python, etc. Real extractors use tree-sitter and are
the only place that pulls the tree-sitter dependency in, keeping M0 dependency
free.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable

from ..model import SourceUnit


class Extractor(ABC):
    """Base class for a per-language source-unit extractor.

    Subclasses declare ``language`` and emit role-typed ``SourceUnit`` objects.
    They must only emit kinds that are registered in ``taxonomy`` so role typing
    stays centralised.
    """

    language: str = ""

    def prescan(self, sources: dict[str, str]) -> dict:
        """Optional whole-language pass before per-file extraction.

        ``sources`` maps path -> text for every file of this language. Return a
        ``context`` dict handed to each ``extract`` call. Default: no context.
        Used e.g. to resolve Pydantic base classes across files.
        """
        return {}

    @abstractmethod
    def extract(
        self,
        path: str,
        source: str,
        id_factory: Callable[[], str],
        framework: str | None = None,
        context: dict | None = None,
    ) -> list[SourceUnit]:
        ...


_REGISTRY: dict[str, Extractor] = {}


def register(extractor: Extractor) -> Extractor:
    """Register an extractor instance under its declared language."""
    if not extractor.language:
        raise ValueError(f"{extractor!r} has no language set")
    _REGISTRY[extractor.language] = extractor
    return extractor


def get_extractor(language: str) -> Extractor | None:
    return _REGISTRY.get(language)


def supported_languages() -> list[str]:
    return sorted(_REGISTRY.keys())


def _autoload() -> None:
    """Import bundled language extractors so they self-register.

    Each module guards its own registration on tree-sitter availability, so a
    missing optional dependency simply leaves that language unregistered (the
    pipeline then falls back to file-level units + a loud warning).
    """
    for mod in ("python_ext", "typescript_ext", "ruby_ext",
                "php_ext", "java_ext", "csharp_ext",
                "go_ext", "sql_ext", "cobol_ext"):
        try:
            __import__(f"{__name__}.{mod}")
        except Exception:
            pass


_autoload()

"""cc-rsg source-map v2 — orchestrator wiring the three layers together.

  layer 1 detect.detect_frameworks(root)
  layer 2 extractors.get_extractor(language).extract(...)
  layer 3 map to taxonomy + assemble SourceMap (with loud warnings)

M0 goal: this runs end to end on any tree and produces a schema-0.2.0 SourceMap.
With no extractors registered yet, source files become file-level fallback units
and each unhandled language raises one warning (deduplicated).
"""

from __future__ import annotations

import fnmatch
from pathlib import Path

from . import detect, extractors
from .model import IdFactory, SourceMap, SourceUnit, fingerprint

DEFAULT_EXCLUDES = [
    "**/.git/**", "**/node_modules/**", "**/vendor/**", "**/vendor/bundle/**",
    "**/tmp/**", "**/log/**", "**/coverage/**", "**/.bundle/**",
    "**/public/assets/**", "**/dist/**", "**/build/**", "**/.venv/**",
    "**/__pycache__/**",
]


def _matches_any(rel: str, globs: list[str]) -> bool:
    return any(fnmatch.fnmatch(rel, g) for g in globs)


def _iter_files(target: Path, exclude_globs: list[str]):
    base = target.parent
    for p in sorted(target.rglob("*")):
        if not p.is_file():
            continue
        rel = str(p.relative_to(base))
        if _matches_any(rel, exclude_globs):
            continue
        yield p, rel


def _file_level_unit(rel: str, source: str, language: str, id_factory) -> SourceUnit:
    """Coarse fallback: one ``module``-role unit for the whole file."""
    lines = source.splitlines()
    return SourceUnit(
        id=id_factory(),
        path=rel,
        line_range=(1, max(len(lines), 1)),
        language=language,
        role="module",
        kind=f"{language}_file",
        tier="macro",
        name=Path(rel).name,
        signature=(lines[0].strip() if lines else Path(rel).name),
        fingerprint=fingerprint(source),
    )


def build_source_map(target: Path, exclude_globs: list[str] | None = None) -> SourceMap:
    exclude_globs = exclude_globs if exclude_globs is not None else list(DEFAULT_EXCLUDES)
    target = target.resolve()
    id_factory = IdFactory()

    # Layer 1: detect frameworks at the PROJECT ROOT (manifests live there),
    # which may be an ancestor of the code dir the user pointed --target at.
    project_root = detect.find_project_root(target)
    hints = detect.detect_frameworks(project_root)
    smap = SourceMap(target_root=target.name, detected_frameworks=hints)

    # Pass 1: gather sources grouped by language (so extractors can prescan).
    by_language: dict[str, list[tuple[str, str]]] = {}
    for path, rel in _iter_files(target, exclude_globs):
        language = detect.language_for_path(rel)
        if language is None:
            smap.files_excluded += 1
            continue
        smap.files_scanned += 1
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        by_language.setdefault(language, []).append((rel, source))

    # Pass 2: per language, prescan then extract (or fall back + warn).
    for language, files in by_language.items():
        extractor = extractors.get_extractor(language)
        if extractor is None:
            smap.warnings.append(
                f"language '{language}' has no v2 extractor yet — emitting file-level units only "
                f"({len(files)} file(s), first: {files[0][0]})"
            )
            for rel, source in files:
                smap.units.append(_file_level_unit(rel, source, language, id_factory))
            continue

        framework = detect.framework_for_language(hints, language)
        context = extractor.prescan({rel: source for rel, source in files})
        for rel, source in files:
            smap.units.extend(
                extractor.extract(rel, source, id_factory, framework=framework, context=context)
            )

    smap.validate()
    return smap

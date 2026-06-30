"""cc-rsg source-map v2 — layer 1: framework detection.

Sniffs project manifests and directory conventions to decide which framework a
language is using, so layer-2 extractors can pick the right query set (e.g. the
same Python ``def`` is an endpoint under FastAPI but a plain callable elsewhere).

Detection is best-effort and never raises: a repo with no recognised manifest
simply yields no framework hints. Each hint records the *evidence* that
triggered it, so the detection result is auditable.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# language -> file extensions (single source of truth for language classification)
LANG_BY_EXT: dict[str, str] = {
    ".rb": "ruby",
    ".py": "python",
    ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".ts": "typescript", ".tsx": "typescript",
    ".php": "php",
    ".java": "java", ".kt": "kotlin",
    ".cs": "csharp",
    ".go": "go",
    ".cob": "cobol", ".cbl": "cobol", ".cpy": "cobol",
    ".sql": "sql",
}


def language_for_path(path: str) -> str | None:
    return LANG_BY_EXT.get(Path(path).suffix.lower())


# Files that mark a project root (where manifests / framework signals live).
ROOT_MARKERS = (
    ".git", "package.json", "pyproject.toml", "setup.py", "setup.cfg",
    "requirements.txt", "Pipfile", "go.mod", "composer.json", "pom.xml",
    "build.gradle", "build.gradle.kts", "Gemfile", "Cargo.toml",
)


def find_project_root(target: Path, max_up: int = 8) -> Path:
    """Walk up from ``target`` to the nearest dir holding a root marker.

    Framework detection must look at the project root (where the manifests are),
    not only at the code subdirectory the user pointed ``--target`` at — e.g.
    ``mealie/mealie`` has no manifest but its parent ``mealie/`` declares FastAPI.
    """
    target = target.resolve()
    cur = target if target.is_dir() else target.parent
    for _ in range(max_up + 1):
        if any((cur / m).exists() for m in ROOT_MARKERS):
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return target if target.is_dir() else target.parent


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _hint(lang: str, framework: str, confidence: str, evidence: str) -> dict[str, Any]:
    return {"lang": lang, "framework": framework, "confidence": confidence, "evidence": evidence}


def detect_frameworks(root: Path) -> list[dict[str, Any]]:
    """Return a list of framework hints for the project rooted at ``root``."""
    hints: list[dict[str, Any]] = []

    # --- JavaScript / TypeScript: package.json dependencies ---
    pkg = root / "package.json"
    if pkg.exists():
        try:
            data = json.loads(_read(pkg) or "{}")
            deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
        except json.JSONDecodeError:
            deps = {}
        for dep, fw in (("next", "nextjs"), ("@nestjs/core", "nestjs"),
                        ("express", "express"), ("fastify", "fastify"),
                        ("hono", "hono"), ("react", "react"),
                        ("vue", "vue"), ("expo", "expo")):
            if dep in deps:
                lang = "typescript" if (root / "tsconfig.json").exists() else "javascript"
                hints.append(_hint(lang, fw, "high", f"{dep} in package.json dependencies"))

    # --- Python: requirements.txt / pyproject.toml ---
    py_manifest_text = ""
    for name in ("requirements.txt", "pyproject.toml", "Pipfile", "setup.cfg"):
        p = root / name
        if p.exists():
            py_manifest_text += "\n" + _read(p)
    low = py_manifest_text.lower()
    for token, fw in (("fastapi", "fastapi"), ("django", "django"), ("flask", "flask"),
                      ("celery", "celery")):
        if token in low:
            hints.append(_hint("python", fw, "high", f"{token} in python manifest"))
    manage_py = root / "manage.py"
    if manage_py.exists():
        body = _read(manage_py).lower()
        # manage.py alone is not proof of Django: pypiserver, for one, ships an
        # unrelated manage.py. Require an actual Django reference in the file.
        if "django" in body or "execute_from_command_line" in body:
            hints.append(_hint("python", "django", "high", "manage.py references django"))

    # --- Ruby on Rails ---
    if (root / "config" / "routes.rb").exists() or (root / "bin" / "rails").exists():
        hints.append(_hint("ruby", "rails", "high", "config/routes.rb or bin/rails present"))

    # --- PHP: composer.json ---
    composer = root / "composer.json"
    if composer.exists():
        low_c = (_read(composer) or "").lower()
        for token, fw in (("laravel/framework", "laravel"), ("symfony/", "symfony"),
                          ("cakephp/", "cakephp")):
            if token in low_c:
                hints.append(_hint("php", fw, "high", f"{token} in composer.json"))

    # --- Java / Kotlin: Spring Boot ---
    for name in ("pom.xml", "build.gradle", "build.gradle.kts"):
        p = root / name
        if p.exists() and "spring-boot" in (_read(p) or "").lower():
            hints.append(_hint("java", "spring-boot", "high", f"spring-boot in {name}"))
            break

    # --- C#: ASP.NET Core ---
    for csproj in root.rglob("*.csproj"):
        if "Microsoft.AspNetCore" in (_read(csproj) or ""):
            hints.append(_hint("csharp", "aspnetcore", "high", f"AspNetCore in {csproj.name}"))
            break

    # --- Go ---
    if (root / "go.mod").exists():
        hints.append(_hint("go", "go", "medium", "go.mod present"))

    return hints


def framework_for_language(hints: list[dict[str, Any]], language: str) -> str | None:
    """Pick the highest-confidence framework hint for a language (or None)."""
    candidates = [h for h in hints if h["lang"] == language]
    if not candidates:
        return None
    order = {"high": 0, "medium": 1, "low": 2}
    candidates.sort(key=lambda h: order.get(h["confidence"], 9))
    return candidates[0]["framework"]

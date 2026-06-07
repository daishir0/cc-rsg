#!/usr/bin/env python3
"""
cc-rsg source-map.py

ターゲット・コードベースを走査し、「ソースユニット」を抽出して
`.cc-rsg/source-map.json` を生成する。

ソースユニットの定義は言語ごとに正規表現で実装する。Tree-sitter は依存を
増やすため v1 では使わず、保守可能な正規表現ベースで実装する。

ソースユニット = 仕様書でトレーサビリティを担保したい最小単位。
- Ruby/Rails:  class / module 単位、controller の action 単位、route group、migration、view
- Python:      class / def 単位
- JavaScript:  export 単位、関数定義
- 他言語:      ファイル単位（粗いがゼロより遥かに良い）

使い方:
    python source-map.py \\
        --target ./src \\
        --output .cc-rsg/source-map.json \\
        --exclude-globs '**/test/**,**/vendor/**,**/node_modules/**'

出力 (source-map.json) スキーマ:
    {
      "schema_version": "0.1.0",
      "target_root": "<input target>",
      "generated_at": "<ISO 8601>",
      "stats": {
        "files_scanned": N,
        "files_excluded": K,
        "units_total": M,
        "by_kind": {"ruby_class": ..., "rails_route": ...}
      },
      "units": [
        {
          "id": "SRC-0001",
          "path": "<relative to repo root>",
          "line_range": [start, end],   // 1-indexed inclusive
          "kind": "ruby_class",
          "name": "Issue",
          "signature": "class Issue < ActiveRecord::Base",
          "fingerprint": "sha1:..."
        },
        ...
      ]
    }
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import re
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


# ----------------------------------------------------------------------------
# ソースユニット定義
# ----------------------------------------------------------------------------

@dataclass
class SourceUnit:
    id: str
    path: str
    line_range: tuple[int, int]
    kind: str
    name: str
    signature: str
    fingerprint: str


# ----------------------------------------------------------------------------
# 言語別抽出ルール
# ----------------------------------------------------------------------------

RUBY_CLASS_RE = re.compile(r"^(\s*)(class|module)\s+([A-Za-z0-9_:]+)([^\n]*)")
RUBY_DEF_RE = re.compile(r"^(\s*)def\s+(self\.)?([A-Za-z_][A-Za-z0-9_!?=]*)([^\n]*)")
PY_CLASS_RE = re.compile(r"^(\s*)class\s+([A-Za-z_][A-Za-z0-9_]*)([^\n]*)")
PY_DEF_RE = re.compile(r"^(\s*)def\s+([A-Za-z_][A-Za-z0-9_]*)([^\n]*)")
JS_EXPORT_RE = re.compile(
    r"^\s*export\s+(?:default\s+)?"
    r"(?:async\s+)?"
    r"(?:function\s+|class\s+|const\s+|let\s+|var\s+)?"
    r"([A-Za-z_][A-Za-z0-9_]*)"
)
RAILS_ROUTE_BLOCK_RE = re.compile(
    r"^(\s*)(resources?|namespace|scope)\s+:?([A-Za-z0-9_]+)"
)


def fingerprint(text: str) -> str:
    return "sha1:" + hashlib.sha1(text.encode("utf-8", errors="replace")).hexdigest()[:16]


def extract_ruby_block(lines: list[str], start_idx: int, indent: str) -> int:
    """
    Ruby の `class`/`module`/`def` ブロックの end までの行番号 (1-indexed) を返す。
    対応する `end` の indent が start と一致する行を見つける。
    """
    end_pattern = re.compile(rf"^{re.escape(indent)}end\b")
    for j in range(start_idx + 1, len(lines)):
        if end_pattern.match(lines[j]):
            return j + 1  # 1-indexed
    return len(lines)


def extract_py_block(lines: list[str], start_idx: int, indent: str) -> int:
    """
    Python ブロック: インデント が start と同じか深い行が続く間、ブロックに含む。
    最初の「インデントが start より浅い行」の手前で打ち切り。
    """
    base = len(indent)
    for j in range(start_idx + 1, len(lines)):
        ln = lines[j]
        if ln.strip() == "":
            continue
        cur_indent = len(ln) - len(ln.lstrip(" "))
        if cur_indent <= base:
            return j  # j-1 が最後の行 (1-indexed なら j)
    return len(lines)


def extract_ruby_units(
    rel_path: str, source: str, id_factory
) -> Iterable[SourceUnit]:
    lines = source.splitlines()
    is_routes = rel_path.endswith("config/routes.rb")

    for i, line in enumerate(lines):
        m_cls = RUBY_CLASS_RE.match(line)
        if m_cls:
            indent, kw, name, rest = m_cls.groups()
            end_line = extract_ruby_block(lines, i, indent)
            block_text = "\n".join(lines[i:end_line])
            yield SourceUnit(
                id=id_factory(),
                path=rel_path,
                line_range=(i + 1, end_line),
                kind=f"ruby_{kw}",
                name=name,
                signature=f"{kw} {name}{rest}".strip(),
                fingerprint=fingerprint(block_text),
            )
            continue

        if is_routes:
            m_route = RAILS_ROUTE_BLOCK_RE.match(line)
            if m_route:
                indent, kw, name = m_route.groups()
                # do…end ブロック対応 / 単行 resources :foo 対応
                if "do" in line and " end" not in line:
                    end_line = extract_ruby_block(lines, i, indent)
                else:
                    end_line = i + 1
                block_text = "\n".join(lines[i:end_line])
                yield SourceUnit(
                    id=id_factory(),
                    path=rel_path,
                    line_range=(i + 1, end_line),
                    kind="rails_route",
                    name=f"{kw}:{name}",
                    signature=line.rstrip(),
                    fingerprint=fingerprint(block_text),
                )


def extract_py_units(rel_path: str, source: str, id_factory) -> Iterable[SourceUnit]:
    lines = source.splitlines()
    for i, line in enumerate(lines):
        m_cls = PY_CLASS_RE.match(line)
        if m_cls:
            indent, name, rest = m_cls.groups()
            end_line = extract_py_block(lines, i, indent)
            block_text = "\n".join(lines[i:end_line])
            yield SourceUnit(
                id=id_factory(),
                path=rel_path,
                line_range=(i + 1, end_line),
                kind="py_class",
                name=name,
                signature=f"class {name}{rest}".strip(),
                fingerprint=fingerprint(block_text),
            )
            continue
        m_def = PY_DEF_RE.match(line)
        if m_def:
            indent, name, rest = m_def.groups()
            # トップレベル def のみユニットとして登録（メソッドは class ブロックに含まれる）
            if indent == "":
                end_line = extract_py_block(lines, i, indent)
                block_text = "\n".join(lines[i:end_line])
                yield SourceUnit(
                    id=id_factory(),
                    path=rel_path,
                    line_range=(i + 1, end_line),
                    kind="py_function",
                    name=name,
                    signature=f"def {name}{rest}".strip(),
                    fingerprint=fingerprint(block_text),
                )


def extract_js_units(rel_path: str, source: str, id_factory) -> Iterable[SourceUnit]:
    lines = source.splitlines()
    for i, line in enumerate(lines):
        m = JS_EXPORT_RE.match(line)
        if m:
            name = m.group(1)
            yield SourceUnit(
                id=id_factory(),
                path=rel_path,
                line_range=(i + 1, i + 1),
                kind="js_export",
                name=name,
                signature=line.strip(),
                fingerprint=fingerprint(line),
            )


def extract_file_unit(rel_path: str, source: str, kind: str, id_factory) -> SourceUnit:
    """ファイル単位の粗いユニット（migration / view / config 等で使用）。"""
    lines = source.splitlines()
    name = Path(rel_path).name
    return SourceUnit(
        id=id_factory(),
        path=rel_path,
        line_range=(1, max(len(lines), 1)),
        kind=kind,
        name=name,
        signature=lines[0].strip() if lines else name,
        fingerprint=fingerprint(source),
    )


# ----------------------------------------------------------------------------
# ファイル分類とディスパッチ
# ----------------------------------------------------------------------------

def classify_file(rel_path: str) -> list[str]:
    """
    ファイルが該当する 1 つ以上の抽出戦略のリストを返す。
    Returns list of strategies like ["ruby_class_def", "rails_view"].
    Empty list = この file はユニット抽出対象外（しかし source map には記録される ── kind="file"）。
    """
    p = rel_path.lower()
    strategies: list[str] = []

    if p.endswith(".rb"):
        strategies.append("ruby_class_def")
        if p.endswith("/config/routes.rb"):
            strategies.append("rails_routes")
        if "/db/migrate/" in p:
            strategies.append("rails_migration")
    elif p.endswith((".py",)):
        strategies.append("py_class_def")
    elif p.endswith((".js", ".jsx", ".ts", ".tsx", ".mjs")):
        strategies.append("js_export")
    elif p.endswith((".erb", ".html.erb", ".html", ".vue", ".svelte")):
        strategies.append("view_file")
    elif p.endswith((".yml", ".yaml", ".toml", ".ini", ".conf", ".cfg")):
        strategies.append("config_file")
    elif p.endswith((".css", ".scss", ".sass", ".less")):
        # スタイル系は粗くファイル単位
        strategies.append("style_file")
    elif p.endswith((".md", ".rst", ".txt", ".rdoc")) and not "readme" in p:
        # 一般 md はスキップ
        return []
    elif p.endswith(".sql"):
        strategies.append("sql_file")

    return strategies


def matches_any(rel_path: str, globs: list[str]) -> bool:
    return any(fnmatch.fnmatch(rel_path, g) for g in globs)


def iter_target_files(target: Path, exclude_globs: list[str]) -> Iterable[Path]:
    for p in target.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(target.parent)
        rel_str = str(rel)
        if matches_any(rel_str, exclude_globs):
            continue
        yield p


# ----------------------------------------------------------------------------
# メイン
# ----------------------------------------------------------------------------

DEFAULT_EXCLUDES = [
    "**/.git/**",
    "**/node_modules/**",
    "**/vendor/bundle/**",
    "**/tmp/**",
    "**/log/**",
    "**/coverage/**",
    "**/.bundle/**",
    "**/public/assets/**",
    "**/dist/**",
    "**/build/**",
]


def build_source_map(
    target_path: Path,
    exclude_globs: list[str],
) -> dict:
    units: list[SourceUnit] = []
    files_scanned = 0
    files_excluded = 0
    next_id = [0]

    def id_factory() -> str:
        next_id[0] += 1
        return f"SRC-{next_id[0]:04d}"

    base = target_path.parent

    for file_path in iter_target_files(target_path, exclude_globs):
        rel_path = str(file_path.relative_to(base))
        strategies = classify_file(rel_path)
        if not strategies:
            files_excluded += 1
            continue
        files_scanned += 1
        try:
            source = file_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            try:
                source = file_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

        for strat in strategies:
            if strat == "ruby_class_def":
                units.extend(extract_ruby_units(rel_path, source, id_factory))
            elif strat == "rails_routes":
                # rails_routes は extract_ruby_units 内でも処理されるので重複避け
                pass
            elif strat == "rails_migration":
                units.append(
                    extract_file_unit(rel_path, source, "rails_migration", id_factory)
                )
            elif strat == "py_class_def":
                units.extend(extract_py_units(rel_path, source, id_factory))
            elif strat == "js_export":
                units.extend(extract_js_units(rel_path, source, id_factory))
            elif strat == "view_file":
                units.append(extract_file_unit(rel_path, source, "view_file", id_factory))
            elif strat == "config_file":
                units.append(extract_file_unit(rel_path, source, "config_file", id_factory))
            elif strat == "style_file":
                units.append(extract_file_unit(rel_path, source, "style_file", id_factory))
            elif strat == "sql_file":
                units.append(extract_file_unit(rel_path, source, "sql_file", id_factory))

    # 統計集計
    by_kind: dict[str, int] = {}
    for u in units:
        by_kind[u.kind] = by_kind.get(u.kind, 0) + 1

    return {
        "schema_version": "0.1.0",
        "target_root": target_path.name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stats": {
            "files_scanned": files_scanned,
            "files_excluded": files_excluded,
            "units_total": len(units),
            "by_kind": by_kind,
        },
        "units": [
            {
                "id": u.id,
                "path": u.path,
                "line_range": list(u.line_range),
                "kind": u.kind,
                "name": u.name,
                "signature": u.signature[:240],  # 長すぎる行は切る
                "fingerprint": u.fingerprint,
            }
            for u in units
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="cc-rsg source map extractor")
    parser.add_argument("--target", required=True, help="Target codebase root (directory)")
    parser.add_argument(
        "--output",
        default=".cc-rsg/source-map.json",
        help="Output path for source-map.json",
    )
    parser.add_argument(
        "--exclude-globs",
        default=",".join(DEFAULT_EXCLUDES),
        help="Comma-separated glob patterns to exclude",
    )
    args = parser.parse_args(argv)

    target_path = Path(args.target).resolve()
    if not target_path.is_dir():
        print(f"ERROR: target not a directory: {target_path}", file=sys.stderr)
        return 2

    exclude_globs = [g.strip() for g in args.exclude_globs.split(",") if g.strip()]
    out = build_source_map(target_path, exclude_globs)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(out, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    stats = out["stats"]
    print(
        f"source-map.py: {stats['units_total']} units extracted from "
        f"{stats['files_scanned']} files (excluded: {stats['files_excluded']}). "
        f"Written to {output_path}"
    )
    print(f"  by kind: {stats['by_kind']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

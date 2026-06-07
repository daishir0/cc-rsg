#!/usr/bin/env python3
"""
cc-rsg build-trace.py

drafts/*.md（or final/*.md）に書かれている `[REF: path:Lstart-Lend]` を全件抽出し、
`.cc-rsg/source-map.json` のソースユニットと突き合わせて
`.cc-rsg/trace.json` を生成する。

これにより:
- 仕様書 → ソース の参照（agent が書いた REF をそのまま記録）
- ソース → 仕様書 の逆引き（by_source インデックス）
- MECE 検証用の covered/excluded/uncovered 集計

を一括で得られる。

使い方:
    python build-trace.py --cc-rsg-dir .cc-rsg [--target-dir-for-required final]

出力 (.cc-rsg/trace.json) スキーマ:
    {
      "schema_version": "0.2.0",
      "generated_at": "<ISO>",
      "source_units_total": N,
      "source_units_covered": C,
      "source_units_excluded": E,
      "source_units_uncovered": U,
      "mece_passed": bool,
      "by_source": {
        "SRC-NNNN": {
          "path": "...",
          "line_range": [s, e],
          "covered_by_sections": [{"file": "05-data-model.md", "section": "..."}],
          "excluded": false,
          "excluded_reason": null
        }
      },
      "by_section": {
        "05-data-model.md::5.2 Issue": ["SRC-0142", ...]
      },
      "uncovered_units": ["SRC-NNNN", ...]
    }

`.cc-rsg/exclusions.yaml` を読んで明示的除外を反映する。YAML が無くてもOK。
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# YAML はオプション（標準ライブラリにないため try/except でフォールバック）
try:
    import yaml  # type: ignore
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


REF_RE = re.compile(r"\[REF:\s*([^:\]]+):(\d+)(?:-(\d+))?\]")
SECTION_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def load_source_map(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"source-map.json not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_exclusions(path: Path) -> list[dict]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    if HAS_YAML:
        data = yaml.safe_load(text) or {}
        return list(data.get("exclusions", []))
    # 簡易 YAML パース: ハイフン区切りでパターンと理由を抽出
    items: list[dict] = []
    current: dict | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            if current:
                items.append(current)
            current = {}
            stripped = stripped[2:].strip()
            if ":" in stripped:
                k, v = stripped.split(":", 1)
                current[k.strip()] = v.strip().strip("\"'")
        elif ":" in stripped and current is not None:
            k, v = stripped.split(":", 1)
            current[k.strip()] = v.strip().strip("\"'")
    if current:
        items.append(current)
    return items


def is_excluded(unit: dict, exclusions: list[dict]) -> tuple[bool, str | None]:
    for ex in exclusions:
        if "source_id" in ex and ex["source_id"] == unit["id"]:
            return True, ex.get("reason", "")
        if "path" in ex and ex["path"] == unit["path"]:
            return True, ex.get("reason", "")
        if "path_glob" in ex and fnmatch.fnmatch(unit["path"], ex["path_glob"]):
            return True, ex.get("reason", "")
    return False, None


def parse_section_at(lines: list[str], line_no_0idx: int) -> str:
    """指定行の前にある最も近い # 見出しを章セクション名として返す。"""
    for i in range(line_no_0idx, -1, -1):
        m = SECTION_RE.match(lines[i])
        if m:
            return m.group(2).strip()
    return "(prelude)"


def scan_drafts_for_refs(drafts_dir: Path) -> list[dict]:
    """drafts/*.md (or final/*.md) 内の [REF: ...] を全件抽出。"""
    out: list[dict] = []
    if not drafts_dir.is_dir():
        return out
    for md_file in sorted(drafts_dir.glob("*.md")):
        try:
            content = md_file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = md_file.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines()
        for line_no_0idx, line in enumerate(lines):
            for m in REF_RE.finditer(line):
                ref_path = m.group(1).strip()
                start = int(m.group(2))
                end = int(m.group(3)) if m.group(3) else start
                section = parse_section_at(lines, line_no_0idx)
                out.append({
                    "draft_file": md_file.name,
                    "section": section,
                    "ref_path": ref_path,
                    "ref_start": start,
                    "ref_end": end,
                })
    return out


def resolve_refs_to_units(refs: list[dict], units: list[dict]) -> dict[str, list[dict]]:
    """各 SRC unit ID に対して、その unit にヒットした REF 一覧を返す。"""
    coverage: dict[str, list[dict]] = {u["id"]: [] for u in units}

    # 高速化のため path で index
    units_by_path: dict[str, list[dict]] = {}
    for u in units:
        units_by_path.setdefault(u["path"], []).append(u)

    for ref in refs:
        # path 部分が完全一致または末尾一致のものを探す
        ref_path = ref["ref_path"]
        candidates: list[dict] = []
        # 完全一致
        if ref_path in units_by_path:
            candidates.extend(units_by_path[ref_path])
        else:
            # 末尾一致（agent が `app/models/issue.rb` と書いて、
            # source-map は `<workspace>/app/models/issue.rb` で記録、のような共通形）
            for path, ulist in units_by_path.items():
                if path.endswith("/" + ref_path) or ref_path.endswith("/" + path):
                    candidates.extend(ulist)

        # 行範囲がオーバーラップする unit に hit
        for unit in candidates:
            u_start, u_end = unit["line_range"]
            r_start, r_end = ref["ref_start"], ref["ref_end"]
            if not (r_end < u_start or r_start > u_end):
                coverage[unit["id"]].append({
                    "file": ref["draft_file"],
                    "section": ref["section"],
                })
    return coverage


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="cc-rsg trace builder")
    parser.add_argument(
        "--cc-rsg-dir",
        default=".cc-rsg",
        help="Path to .cc-rsg/ directory",
    )
    parser.add_argument(
        "--target-dir-for-required",
        default="final",
        choices=["drafts", "final"],
        help="Which directory to scan for [REF:] markers (drafts or final)",
    )
    args = parser.parse_args(argv)

    cc_rsg = Path(args.cc_rsg_dir)
    source_map_path = cc_rsg / "source-map.json"
    drafts_dir = cc_rsg / args.target_dir_for_required
    output_path = cc_rsg / "trace.json"
    exclusions_path = cc_rsg / "exclusions.yaml"

    if not source_map_path.exists():
        print(
            f"ERROR: {source_map_path} not found. Run scripts/source-map.py first.",
            file=sys.stderr,
        )
        return 2

    sm = load_source_map(source_map_path)
    units = sm.get("units", [])
    exclusions = load_exclusions(exclusions_path)

    refs = scan_drafts_for_refs(drafts_dir)
    coverage = resolve_refs_to_units(refs, units)

    by_source: dict[str, dict[str, Any]] = {}
    by_section: dict[str, list[str]] = {}
    uncovered: list[str] = []
    covered_count = 0
    excluded_count = 0

    for u in units:
        excluded, reason = is_excluded(u, exclusions)
        sections = coverage.get(u["id"], [])
        # 章セクション内重複は1つにまとめる
        uniq_sections: list[dict[str, str]] = []
        seen = set()
        for s in sections:
            key = (s["file"], s["section"])
            if key not in seen:
                seen.add(key)
                uniq_sections.append(s)

        by_source[u["id"]] = {
            "path": u["path"],
            "line_range": u["line_range"],
            "kind": u["kind"],
            "name": u["name"],
            "covered_by_sections": uniq_sections,
            "excluded": excluded,
            "excluded_reason": reason,
        }
        if uniq_sections:
            covered_count += 1
            for s in uniq_sections:
                key = f"{s['file']}::{s['section']}"
                by_section.setdefault(key, []).append(u["id"])
        elif excluded:
            excluded_count += 1
        else:
            uncovered.append(u["id"])

    total = len(units)
    uncovered_count = len(uncovered)
    mece_passed = uncovered_count == 0

    trace = {
        "schema_version": "0.2.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_units_total": total,
        "source_units_covered": covered_count,
        "source_units_excluded": excluded_count,
        "source_units_uncovered": uncovered_count,
        "mece_passed": mece_passed,
        "by_source": by_source,
        "by_section": by_section,
        "uncovered_units": uncovered,
    }
    output_path.write_text(
        json.dumps(trace, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(
        f"build-trace.py: total={total} covered={covered_count} "
        f"excluded={excluded_count} uncovered={uncovered_count} "
        f"mece_passed={mece_passed}"
    )
    if uncovered:
        print(f"  uncovered SRC sample: {uncovered[:5]}", file=sys.stderr)
    return 0 if mece_passed else 1


if __name__ == "__main__":
    sys.exit(main())

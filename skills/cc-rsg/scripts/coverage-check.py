#!/usr/bin/env python3
"""
cc-rsg coverage-check.py

Phase 4(Verify)で実行する検証スクリプト。
inventory.json の各項目が drafts/ 配下のいずれかの章で言及されているかを照合し、
未言及項目をリスト化する。同時に Question Bank の整合性チェックも実施する。

使い方:
    python coverage-check.py [--cc-rsg-dir PATH] [--output-format text|json]

デフォルトでは current working directory の .cc-rsg/ を対象とする。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class InventoryItem:
    id: str
    type: str
    name: str
    file: str
    line: int | None
    covered_by: list[str]


@dataclass
class CoverageReport:
    total_inventory: int
    covered: int
    uncovered: list[InventoryItem]
    coverage_rate: float
    drafts_scanned: int
    questions_total: int
    questions_open: int
    questions_blocked_referenced: list[str]
    integrity_issues: list[str]


def load_inventory(inventory_path: Path) -> list[InventoryItem]:
    if not inventory_path.exists():
        raise FileNotFoundError(f"inventory.json not found at {inventory_path}")
    data = json.loads(inventory_path.read_text(encoding="utf-8"))
    items: list[InventoryItem] = []
    for entry in data.get("units", []):
        items.append(
            InventoryItem(
                id=entry["id"],
                type=entry.get("type", ""),
                name=entry["name"],
                file=entry.get("file", ""),
                line=entry.get("line"),
                covered_by=list(entry.get("covered_by", [])),
            )
        )
    return items


def load_questions(questions_path: Path) -> list[dict[str, Any]]:
    if not questions_path.exists():
        return []
    data = json.loads(questions_path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return list(data.get("questions", []))
    if isinstance(data, list):
        return data
    return []


def scan_drafts(drafts_dir: Path) -> dict[str, str]:
    """各 draft Markdown ファイルの内容を読み込んでファイル名→内容の辞書を返す。"""
    if not drafts_dir.exists() or not drafts_dir.is_dir():
        return {}
    contents: dict[str, str] = {}
    for md_file in sorted(drafts_dir.rglob("*.md")):
        try:
            contents[md_file.name] = md_file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            contents[md_file.name] = md_file.read_text(encoding="utf-8", errors="replace")
    return contents


def detect_mentions(item: InventoryItem, drafts: dict[str, str]) -> list[str]:
    """インベントリ項目が言及されている draft ファイル名のリストを返す。

    判定基準は以下のいずれか:
    - インベントリ ID(例: INV-042)が draft 内に含まれる
    - インベントリ name が draft 内に含まれる(単語境界を意識)
    - インベントリ file パスが draft 内に含まれる
    """
    mentioned_in: list[str] = []
    name_pattern = re.compile(rf"\b{re.escape(item.name)}\b")
    for draft_name, content in drafts.items():
        if item.id and item.id in content:
            mentioned_in.append(draft_name)
            continue
        if item.name and name_pattern.search(content):
            mentioned_in.append(draft_name)
            continue
        if item.file and item.file in content:
            mentioned_in.append(draft_name)
            continue
    return mentioned_in


def check_question_integrity(
    questions: list[dict[str, Any]],
    inventory_ids: set[str],
    drafts: dict[str, str],
) -> tuple[list[str], list[str]]:
    """Question Bank の整合性を検証する。

    Returns:
        (issues, blocked_referenced) のタプル。
        issues: 整合性問題のメッセージリスト
        blocked_referenced: drafts 内で [BLOCKED: see Q-XXX] として参照されている Q-ID のうち、
                            実際に questions.json に存在するものの ID リスト
    """
    issues: list[str] = []
    required_fields = {"id", "category", "body", "severity", "status"}
    valid_severities = {"critical", "important", "nice-to-have"}
    valid_statuses = {"open", "asked", "answered", "abandoned"}

    question_ids: set[str] = set()
    for q in questions:
        qid = q.get("id", "<no-id>")
        question_ids.add(qid)
        missing = required_fields - set(q.keys())
        if missing:
            issues.append(f"{qid}: 必須フィールド不足: {sorted(missing)}")
        sev = q.get("severity")
        if sev and sev not in valid_severities:
            issues.append(f"{qid}: 不正な severity 値: {sev}")
        st = q.get("status")
        if st and st not in valid_statuses:
            issues.append(f"{qid}: 不正な status 値: {st}")
        if st == "answered":
            if not q.get("answer"):
                issues.append(f"{qid}: status=answered だが answer が空")
            if not q.get("answered_at"):
                issues.append(f"{qid}: status=answered だが answered_at が空")
        related_inv = q.get("related_inventory_ids", []) or []
        for inv_id in related_inv:
            if inv_id not in inventory_ids:
                issues.append(
                    f"{qid}: related_inventory_ids の {inv_id} が inventory.json に存在しない"
                )

    blocked_pattern = re.compile(r"\[BLOCKED:\s*see\s+(Q-[A-Za-z0-9_-]+)\]")
    blocked_referenced: list[str] = []
    for content in drafts.values():
        for match in blocked_pattern.finditer(content):
            ref_id = match.group(1)
            if ref_id not in question_ids:
                issues.append(f"draft 内 [BLOCKED: see {ref_id}] が questions.json に存在しない")
            else:
                blocked_referenced.append(ref_id)

    return issues, sorted(set(blocked_referenced))


def build_report(cc_rsg_dir: Path) -> CoverageReport:
    inventory_path = cc_rsg_dir / "inventory.json"
    questions_path = cc_rsg_dir / "questions.json"
    drafts_dir = cc_rsg_dir / "drafts"

    inventory = load_inventory(inventory_path)
    drafts = scan_drafts(drafts_dir)
    questions = load_questions(questions_path)
    inventory_ids = {item.id for item in inventory}

    uncovered: list[InventoryItem] = []
    for item in inventory:
        mentioned_in = detect_mentions(item, drafts)
        item.covered_by = mentioned_in
        if not mentioned_in:
            uncovered.append(item)

    integrity_issues, blocked_referenced = check_question_integrity(
        questions, inventory_ids, drafts
    )

    open_q = sum(1 for q in questions if q.get("status") == "open")

    total = len(inventory)
    covered = total - len(uncovered)
    rate = (covered / total * 100.0) if total > 0 else 0.0

    return CoverageReport(
        total_inventory=total,
        covered=covered,
        uncovered=uncovered,
        coverage_rate=rate,
        drafts_scanned=len(drafts),
        questions_total=len(questions),
        questions_open=open_q,
        questions_blocked_referenced=blocked_referenced,
        integrity_issues=integrity_issues,
    )


def render_text(report: CoverageReport) -> str:
    lines: list[str] = []
    lines.append("=== cc-rsg Phase 4 検証レポート ===")
    lines.append("")
    lines.append("【インベントリカバレッジ】")
    lines.append(f"- 全インベントリ項目: {report.total_inventory} 件")
    lines.append(f"- 言及あり: {report.covered} 件 ({report.coverage_rate:.1f}%)")
    lines.append(f"- 未言及: {len(report.uncovered)} 件")
    if report.uncovered:
        for item in report.uncovered[:50]:
            line_info = f":{item.line}" if item.line else ""
            lines.append(f"  - {item.id} {item.name} ({item.file}{line_info})")
        if len(report.uncovered) > 50:
            lines.append(f"  ... 他 {len(report.uncovered) - 50} 件")
    lines.append("")
    lines.append(f"【Drafts スキャン】")
    lines.append(f"- スキャンした draft ファイル数: {report.drafts_scanned} 件")
    lines.append("")
    lines.append("【Question Bank】")
    lines.append(f"- 全疑問: {report.questions_total} 件")
    lines.append(f"- open: {report.questions_open} 件")
    lines.append(
        f"- draft 内 [BLOCKED] 参照済み Q-ID: {len(report.questions_blocked_referenced)} 件"
    )
    lines.append("")
    lines.append("【整合性チェック】")
    if report.integrity_issues:
        for issue in report.integrity_issues:
            lines.append(f"- {issue}")
    else:
        lines.append("- 問題なし")
    return "\n".join(lines)


def render_json(report: CoverageReport) -> str:
    return json.dumps(
        {
            "total_inventory": report.total_inventory,
            "covered": report.covered,
            "coverage_rate": report.coverage_rate,
            "drafts_scanned": report.drafts_scanned,
            "uncovered": [
                {
                    "id": item.id,
                    "type": item.type,
                    "name": item.name,
                    "file": item.file,
                    "line": item.line,
                }
                for item in report.uncovered
            ],
            "questions_total": report.questions_total,
            "questions_open": report.questions_open,
            "questions_blocked_referenced": report.questions_blocked_referenced,
            "integrity_issues": report.integrity_issues,
        },
        ensure_ascii=False,
        indent=2,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="cc-rsg Phase 4 検証スクリプト: inventory と drafts のカバレッジ照合"
    )
    parser.add_argument(
        "--cc-rsg-dir",
        type=Path,
        default=Path.cwd() / ".cc-rsg",
        help="対象の .cc-rsg/ ディレクトリパス(デフォルト: ./.cc-rsg)",
    )
    parser.add_argument(
        "--output-format",
        choices=["text", "json"],
        default="text",
        help="出力フォーマット(デフォルト: text)",
    )
    parser.add_argument(
        "--fail-on-uncovered",
        action="store_true",
        help="未言及インベントリ項目があれば exit code 1 で終了する",
    )
    args = parser.parse_args()

    try:
        report = build_report(args.cc_rsg_dir)
    except FileNotFoundError as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 2

    if args.output_format == "json":
        print(render_json(report))
    else:
        print(render_text(report))

    if args.fail_on_uncovered and report.uncovered:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

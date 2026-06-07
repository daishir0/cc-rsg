#!/usr/bin/env python3
"""
cc-rsg coverage-check.py

Phase 4 (Verify) で実行する検証スクリプト。
インベントリ言及だけでなく、各章の品質指標 (REF 数 / 行数 / コードブロック数 / Mermaid 図数 /
Sources Read セクション等) と Question Bank の整合性、MECE 検査、outline モードでの
全 entity 列挙チェックを一括で実施する。

以下を検証する:

1.  各章の `[REF: path:Lstart-Lend]` 数 (`--min-refs-per-chapter`)
2.  各章の本文行数 (`--min-lines-per-chapter`)
3.  各章の fenced code block 数 (`--min-code-blocks-per-chapter`)
4.  各章の Mermaid 図数 (`--min-mermaid-per-chapter`)
5.  各章冒頭の `## Sources Read` セクションのファイル数 (`--min-sources-read-per-chapter`)
6.  inventory.json 総数の自動最小値 = max(50, file_count // 20)  (`--min-inventory`)
7.  controller_group 等のグルーピング型 INV の比率上限 (`--max-macro-ratio`)
8.  questions.json 総件数 (`--min-questions`)
9.  Phase 5 経過後の `status: open` 比率上限 (`--max-open-ratio`)
10. inventory.covered_by 充填率 (`--min-covered-by-fill`)
11. MECE 検査 (`.cc-rsg/trace.json` を参照、`--min-mece-coverage`)

旧版互換のため `--fail-on-uncovered` `--strict` `--output-format` は維持。
新しい検査群は全て exit 1 で fail を返す。閾値はすべて CLI 引数で上書き可能。

使い方:
    python coverage-check.py \\
      --cc-rsg-dir .cc-rsg \\
      --target-dir-for-required final \\
      --min-refs-per-chapter 10 \\
      --min-lines-per-chapter 200 \\
      --min-code-blocks-per-chapter 3 \\
      --min-mermaid-per-chapter 1 \\
      --min-sources-read-per-chapter 5 \\
      --min-inventory auto \\
      --max-macro-ratio 0.2 \\
      --min-questions 10 \\
      --max-open-ratio 0.2 \\
      --min-covered-by-fill 0.9 \\
      --min-mece-coverage 0.7

Exit codes:
    0 = すべての検査 PASS
    1 = 1つ以上の検査 FAIL
    2 = inventory.json 等の必須ファイル読込エラー
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ----------------------------------------------------------------------------
# 章ファイル命名規約
# ----------------------------------------------------------------------------

NAMING_PATTERN = re.compile(r"^(0\d|[1-9]\d)-[a-z0-9-]+\.md$")
NAMING_EXEMPT = {"traceability.md", "README.md"}
REQUIRED_FILES = ("00-metadata.md", "99-unresolved.md", "traceability.md")

# 章本文内の正規表現
REF_RE = re.compile(r"\[REF:\s*([^:\]]+):(\d+)(?:-(\d+))?\]")
CODE_FENCE_RE = re.compile(r"^```([a-zA-Z0-9_-]+)?")
MERMAID_FENCE_RE = re.compile(r"^```mermaid\b")
SOURCES_READ_RE = re.compile(r"^##+\s*Sources\s*Read\b", re.IGNORECASE)
SOURCES_READ_ITEM_RE = re.compile(r"^\s*[-*]\s+`?([^`\n]+?)`?(?:\s*\([^)]*\))?\s*$")

# macro 系 INV と見なすキーワード（type フィールドに含まれる）
MACRO_TYPE_KEYWORDS = ("group", "module", "domain", "category", "bundle", "section")


# ----------------------------------------------------------------------------
# データクラス
# ----------------------------------------------------------------------------

@dataclass
class InventoryItem:
    id: str
    type: str
    name: str
    file: str
    line: int | None
    covered_by: list[str] = field(default_factory=list)


@dataclass
class ChapterMetrics:
    file: str
    total_lines: int
    body_lines: int
    refs: int
    code_blocks: int
    mermaid_blocks: int
    sources_read_count: int
    failures: list[str] = field(default_factory=list)


@dataclass
class CoverageReport:
    # 旧版互換
    total_inventory: int = 0
    covered: int = 0
    uncovered: list[InventoryItem] = field(default_factory=list)
    coverage_rate: float = 0.0
    drafts_scanned: int = 0
    questions_total: int = 0
    questions_open: int = 0
    questions_blocked_referenced: list[str] = field(default_factory=list)
    integrity_issues: list[str] = field(default_factory=list)
    naming_warnings: list[str] = field(default_factory=list)
    missing_required: list[str] = field(default_factory=list)
    target_dir_for_required: str = ""
    # 新規
    chapter_metrics: list[ChapterMetrics] = field(default_factory=list)
    inventory_required_min: int = 0
    macro_inventory_ratio: float = 0.0
    macro_inventory_count: int = 0
    covered_by_fill_rate: float = 0.0
    open_question_ratio: float = 0.0
    mece_total: int = 0
    mece_covered: int = 0
    mece_excluded: int = 0
    mece_uncovered: int = 0
    mece_passed_strict: bool = True
    mece_coverage_rate: float = 0.0
    gate_failures: list[str] = field(default_factory=list)
    # outline / interactive 用
    depth_mode: str = "comprehensive"
    confidence_verified: int = 0
    confidence_inferred: int = 0
    confidence_assumed: int = 0


# ----------------------------------------------------------------------------
# ローダ
# ----------------------------------------------------------------------------

def load_inventory(path: Path) -> list[InventoryItem]:
    if not path.exists():
        raise FileNotFoundError(f"inventory.json not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
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


def load_questions(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return list(data.get("questions", []))
    if isinstance(data, list):
        return data
    return []


def load_source_map_count(cc_rsg_dir: Path) -> int | None:
    """source-map.json があれば対象ファイル総数を返す（min-inventory auto 算出用）。"""
    sm = cc_rsg_dir / "source-map.json"
    if not sm.exists():
        return None
    try:
        data = json.loads(sm.read_text(encoding="utf-8"))
        return int(data.get("stats", {}).get("files_scanned", 0))
    except Exception:
        return None


def load_trace(cc_rsg_dir: Path) -> dict[str, Any] | None:
    t = cc_rsg_dir / "trace.json"
    if not t.exists():
        return None
    return json.loads(t.read_text(encoding="utf-8"))


def scan_chapter_files(target_dir: Path) -> dict[str, str]:
    """対象ディレクトリ直下の .md ファイル名 → 内容 マップ。"""
    if not target_dir.exists() or not target_dir.is_dir():
        return {}
    out: dict[str, str] = {}
    for md in sorted(target_dir.glob("*.md")):
        try:
            out[md.name] = md.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            out[md.name] = md.read_text(encoding="utf-8", errors="replace")
    return out


# ----------------------------------------------------------------------------
# 章メトリクス算出
# ----------------------------------------------------------------------------

def compute_chapter_metrics(name: str, content: str) -> ChapterMetrics:
    raw_lines = content.splitlines()
    total = len(raw_lines)

    # 本文行 = 空行・コードフェンス・自動生成コメント を除いた行数
    in_code = False
    body_lines = 0
    code_blocks = 0
    mermaid_blocks = 0
    refs = 0
    sources_read_count = 0
    in_sources_read = False

    for line in raw_lines:
        if CODE_FENCE_RE.match(line):
            if not in_code:
                in_code = True
                if MERMAID_FENCE_RE.match(line):
                    mermaid_blocks += 1
                else:
                    code_blocks += 1
            else:
                in_code = False
            continue
        if in_code:
            continue
        stripped = line.strip()
        if not stripped:
            in_sources_read = False  # 空行で Sources Read セクション終了
            continue
        if SOURCES_READ_RE.match(line):
            in_sources_read = True
            continue
        if in_sources_read:
            if SOURCES_READ_ITEM_RE.match(line):
                sources_read_count += 1
            else:
                # 次の見出しが来たら終了
                if line.startswith("#"):
                    in_sources_read = False
            continue
        body_lines += 1
        refs += len(REF_RE.findall(line))

    return ChapterMetrics(
        file=name,
        total_lines=total,
        body_lines=body_lines,
        refs=refs,
        code_blocks=code_blocks,
        mermaid_blocks=mermaid_blocks,
        sources_read_count=sources_read_count,
    )


def evaluate_chapter_gates(
    metrics: list[ChapterMetrics],
    *,
    min_refs: int,
    min_lines: int,
    min_code_blocks: int,
    min_mermaid: int,
    min_sources_read: int,
) -> None:
    """各 ChapterMetrics に failures を populate する（章閾値違反）。"""
    skipped_files = {"00-metadata.md", "99-unresolved.md", "traceability.md", "README.md"}
    for m in metrics:
        if m.file in skipped_files:
            continue
        if m.refs < min_refs:
            m.failures.append(f"[REF:] が {m.refs} 個 < {min_refs} 個必要")
        if m.body_lines < min_lines:
            m.failures.append(f"本文行 {m.body_lines} 行 < {min_lines} 行必要")
        if m.code_blocks < min_code_blocks:
            m.failures.append(f"コードブロック {m.code_blocks} 個 < {min_code_blocks} 個必要")
        if m.mermaid_blocks < min_mermaid:
            m.failures.append(f"Mermaid {m.mermaid_blocks} 個 < {min_mermaid} 個必要")
        if m.sources_read_count < min_sources_read:
            m.failures.append(
                f"Sources Read 項目 {m.sources_read_count} 件 < {min_sources_read} 件必要"
            )


# ----------------------------------------------------------------------------
# 既存ロジック（macro比率・命名・INV mentioned 等）
# ----------------------------------------------------------------------------

def detect_mentions(item: InventoryItem, drafts: dict[str, str]) -> list[str]:
    mentioned_in: list[str] = []
    name_pattern = re.compile(rf"\b{re.escape(item.name)}\b") if item.name else None
    for draft_name, content in drafts.items():
        if item.id and item.id in content:
            mentioned_in.append(draft_name)
            continue
        if name_pattern and name_pattern.search(content):
            mentioned_in.append(draft_name)
            continue
        if item.file and item.file in content:
            mentioned_in.append(draft_name)
            continue
    return mentioned_in


def is_macro_type(item: InventoryItem) -> bool:
    return any(k in item.type.lower() for k in MACRO_TYPE_KEYWORDS)


def check_question_integrity(
    questions: list[dict[str, Any]],
    inventory_ids: set[str],
    drafts: dict[str, str],
) -> tuple[list[str], list[str]]:
    issues: list[str] = []
    required_fields = {"id", "category", "body", "severity", "status"}
    valid_severities = {"critical", "important", "nice-to-have"}
    valid_statuses = {"open", "asked", "answered", "abandoned", "skipped"}

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


def check_naming_convention(drafts_dir: Path) -> list[str]:
    if not drafts_dir.exists() or not drafts_dir.is_dir():
        return []
    warnings: list[str] = []
    for f in sorted(drafts_dir.glob("*.md")):
        if f.name in NAMING_EXEMPT:
            continue
        if not NAMING_PATTERN.match(f.name):
            warnings.append(
                f"{f.name} は命名規約 ({NAMING_PATTERN.pattern}) または予約 {sorted(NAMING_EXEMPT)} に違反"
            )
    return warnings


def check_required_files(target_dir: Path) -> list[str]:
    missing: list[str] = []
    if not target_dir.exists():
        return [f"対象ディレクトリ {target_dir} が存在しない"]
    for required in REQUIRED_FILES:
        if not (target_dir / required).exists():
            missing.append(f"必須ファイル {required} が {target_dir} に存在しない")
    return missing


# ----------------------------------------------------------------------------
# レポート構築
# ----------------------------------------------------------------------------

def detect_depth_mode(cc_rsg_dir: Path) -> str:
    """Read goal.json (if present) and return the configured depth_mode.

    Returns "comprehensive" when the field is missing — that preserves the
    legacy behaviour for projects that pre-date the outline mode flag.
    """
    goal_path = cc_rsg_dir / "goal.json"
    if not goal_path.exists():
        return "comprehensive"
    try:
        with goal_path.open() as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return "comprehensive"
    mode = data.get("depth_mode")
    if mode not in {"comprehensive", "outline", "interactive"}:
        return "comprehensive"
    return mode


def build_report(
    cc_rsg_dir: Path,
    *,
    target_dir_name: str,
    min_inventory: str | int,
    max_macro_ratio: float,
    min_questions: int,
    max_open_ratio: float,
    min_covered_by_fill: float,
    min_refs_per_chapter: int,
    min_lines_per_chapter: int,
    min_code_blocks_per_chapter: int,
    min_mermaid_per_chapter: int,
    min_sources_read_per_chapter: int,
    min_mece_coverage: float,
) -> CoverageReport:
    target_dir = cc_rsg_dir / target_dir_name
    inventory_path = cc_rsg_dir / "inventory.json"
    questions_path = cc_rsg_dir / "questions.json"

    inventory = load_inventory(inventory_path)
    questions = load_questions(questions_path)
    chapters = scan_chapter_files(target_dir)
    inventory_ids = {item.id for item in inventory}

    depth_mode = detect_depth_mode(cc_rsg_dir)

    # 旧版互換: 言及検出
    uncovered: list[InventoryItem] = []
    for item in inventory:
        # covered_by 既存値があれば優先（agent が手動充填した場合）
        if not item.covered_by:
            item.covered_by = detect_mentions(item, chapters)
        if not item.covered_by:
            uncovered.append(item)

    integrity_issues, blocked_referenced = check_question_integrity(
        questions, inventory_ids, chapters
    )

    naming_warnings = check_naming_convention(target_dir)
    missing_required = check_required_files(target_dir)

    # 章メトリクス
    chapter_metrics: list[ChapterMetrics] = []
    for name, content in chapters.items():
        chapter_metrics.append(compute_chapter_metrics(name, content))

    # outline / interactive モードでは comprehensive 用の章ゲート(200行 / REF 10件 /
    # コードブロック / Mermaid / Sources Read 5件) は撤廃。代わりに「全 entity が
    # 表のいずれかの行に存在するか」を MECE 検査基準にする(下の uncovered ロジック
    # を流用)。
    if depth_mode == "comprehensive":
        evaluate_chapter_gates(
            chapter_metrics,
            min_refs=min_refs_per_chapter,
            min_lines=min_lines_per_chapter,
            min_code_blocks=min_code_blocks_per_chapter,
            min_mermaid=min_mermaid_per_chapter,
            min_sources_read=min_sources_read_per_chapter,
        )

    # inventory min auto
    if min_inventory == "auto":
        file_count = load_source_map_count(cc_rsg_dir) or 0
        required_min = max(50, file_count // 20)
    else:
        required_min = int(min_inventory)

    # macro 比率
    macro_count = sum(1 for it in inventory if is_macro_type(it))
    macro_ratio = (macro_count / len(inventory)) if inventory else 0.0

    # covered_by 充填率
    covered_by_filled = sum(1 for it in inventory if it.covered_by)
    covered_by_fill_rate = (covered_by_filled / len(inventory)) if inventory else 0.0

    # questions ratio
    open_q = sum(1 for q in questions if q.get("status") == "open")
    open_ratio = (open_q / len(questions)) if questions else 0.0

    # MECE
    trace = load_trace(cc_rsg_dir)
    mece_total = mece_covered = mece_excluded = mece_uncovered = 0
    mece_passed = True
    mece_rate = 0.0
    if trace is not None:
        mece_total = trace.get("source_units_total", 0)
        mece_covered = trace.get("source_units_covered", 0)
        mece_excluded = trace.get("source_units_excluded", 0)
        mece_uncovered = trace.get("source_units_uncovered", 0)
        denom = max(mece_total - mece_excluded, 1)
        mece_rate = mece_covered / denom
        mece_passed = mece_uncovered == 0

    # ゲート評価
    gate_failures: list[str] = []
    if len(inventory) < required_min:
        gate_failures.append(
            f"inventory.json 件数 {len(inventory)} < 最低 {required_min} 件 "
            f"(コードベース規模に対して粒度不足の可能性)"
        )
    if macro_ratio > max_macro_ratio:
        gate_failures.append(
            f"macro 型 INV 比率 {macro_ratio:.1%} > 上限 {max_macro_ratio:.1%} "
            f"({macro_count}/{len(inventory)} 件が group/module 系。粒度を細分化してください)"
        )
    if covered_by_fill_rate < min_covered_by_fill:
        gate_failures.append(
            f"inventory.covered_by 充填率 {covered_by_fill_rate:.1%} < {min_covered_by_fill:.1%}"
        )
    if len(questions) < min_questions:
        gate_failures.append(
            f"questions.json 件数 {len(questions)} < 最低 {min_questions} 件 "
            f"(Phase 5 対話のため疑問を増やしてください)"
        )
    if questions and open_ratio > max_open_ratio:
        gate_failures.append(
            f"open status 比率 {open_ratio:.1%} > 上限 {max_open_ratio:.1%} "
            f"(Phase 5 三段階対話を完遂してください)"
        )
    if trace is not None and mece_rate < min_mece_coverage:
        gate_failures.append(
            f"MECE カバレッジ {mece_rate:.1%} < {min_mece_coverage:.1%} "
            f"(uncovered={mece_uncovered}/{mece_total - mece_excluded})"
        )
    if trace is None:
        gate_failures.append(
            "trace.json が無い。build-trace.py を実行して MECE 検査を有効化してください"
        )

    # 章メトリクス fail を全体 fail にも反映
    for m in chapter_metrics:
        if m.failures:
            for f in m.failures:
                gate_failures.append(f"章 {m.file}: {f}")

    # outline / interactive モードの confidence ラベル集計
    # 章本文に 🟢 VERIFIED / 🟡 INFERRED / 🔴 ASSUMED が何回出るかを数える
    verified = inferred = assumed = 0
    if depth_mode != "comprehensive":
        for _, content in chapters.items():
            verified += content.count("🟢") + content.count("VERIFIED")
            inferred += content.count("🟡") + content.count("INFERRED")
            assumed  += content.count("🔴") + content.count("ASSUMED")
        # ASSUMED 比率が高すぎる場合は警告
        total_labels = verified + inferred + assumed
        if total_labels > 0:
            assumed_ratio = assumed / total_labels
            if assumed_ratio > 0.6:
                gate_failures.append(
                    f"[outline] ASSUMED 比率が {assumed_ratio:.0%} "
                    f"(60% 超) — 機械抽出による grounding を強化してください"
                )

    total = len(inventory)
    rate = (len(inventory) - len(uncovered)) / total * 100 if total else 0.0

    return CoverageReport(
        total_inventory=total,
        covered=total - len(uncovered),
        uncovered=uncovered,
        coverage_rate=rate,
        drafts_scanned=len(chapters),
        questions_total=len(questions),
        questions_open=open_q,
        questions_blocked_referenced=blocked_referenced,
        integrity_issues=integrity_issues,
        naming_warnings=naming_warnings,
        missing_required=missing_required,
        target_dir_for_required=str(target_dir),
        chapter_metrics=chapter_metrics,
        inventory_required_min=required_min,
        macro_inventory_ratio=macro_ratio,
        macro_inventory_count=macro_count,
        covered_by_fill_rate=covered_by_fill_rate,
        open_question_ratio=open_ratio,
        mece_total=mece_total,
        mece_covered=mece_covered,
        mece_excluded=mece_excluded,
        mece_uncovered=mece_uncovered,
        mece_passed_strict=mece_passed,
        mece_coverage_rate=mece_rate,
        gate_failures=gate_failures,
        depth_mode=depth_mode,
        confidence_verified=verified,
        confidence_inferred=inferred,
        confidence_assumed=assumed,
    )


# ----------------------------------------------------------------------------
# レンダリング
# ----------------------------------------------------------------------------

def render_text(report: CoverageReport) -> str:
    lines: list[str] = []
    lines.append("=== cc-rsg Phase 4 検証レポート ===")
    lines.append("")
    lines.append(f"【depth モード】 {report.depth_mode}")
    if report.depth_mode != "comprehensive":
        total_labels = (
            report.confidence_verified
            + report.confidence_inferred
            + report.confidence_assumed
        )
        if total_labels > 0:
            v_pct = report.confidence_verified / total_labels * 100
            i_pct = report.confidence_inferred / total_labels * 100
            a_pct = report.confidence_assumed / total_labels * 100
            lines.append(
                f"  Confidence KPI: 🟢 VERIFIED {report.confidence_verified} ({v_pct:.0f}%) / "
                f"🟡 INFERRED {report.confidence_inferred} ({i_pct:.0f}%) / "
                f"🔴 ASSUMED {report.confidence_assumed} ({a_pct:.0f}%)"
            )
        else:
            lines.append("  Confidence KPI: ラベル未検出 — 各表セルに 🟢/🟡/🔴 を付与してください")
    lines.append("")
    lines.append("【インベントリカバレッジ】")
    lines.append(f"- 全 inventory 項目: {report.total_inventory} 件 (必要最低: {report.inventory_required_min} 件)")
    lines.append(f"- 言及あり: {report.covered} 件 ({report.coverage_rate:.1f}%)")
    lines.append(f"- 未言及: {len(report.uncovered)} 件")
    lines.append(f"- macro 型: {report.macro_inventory_count} 件 ({report.macro_inventory_ratio:.1%})")
    lines.append(f"- covered_by 充填率: {report.covered_by_fill_rate:.1%}")
    lines.append("")
    lines.append("【MECE 検査】")
    if report.mece_total > 0:
        lines.append(f"- ソースユニット総数: {report.mece_total}")
        lines.append(f"- 仕様書でカバー: {report.mece_covered} ({report.mece_coverage_rate:.1%})")
        lines.append(f"- 明示的除外: {report.mece_excluded}")
        lines.append(f"- 未カバー: {report.mece_uncovered}")
    else:
        lines.append("- trace.json が無いため MECE 未検査")
    lines.append("")
    lines.append("【Question Bank】")
    lines.append(f"- 全件数: {report.questions_total}")
    lines.append(f"- open 残: {report.questions_open} ({report.open_question_ratio:.1%})")
    lines.append("")
    lines.append("【章ごとの品質メトリクス】")
    for m in report.chapter_metrics:
        flag = "❌" if m.failures else "✅"
        lines.append(
            f"  {flag} {m.file}: body={m.body_lines}行 refs={m.refs} "
            f"code={m.code_blocks} mermaid={m.mermaid_blocks} sources_read={m.sources_read_count}"
        )
        for f in m.failures:
            lines.append(f"      - {f}")
    lines.append("")
    lines.append("【ゲート判定】")
    if not report.gate_failures and not report.missing_required:
        lines.append("- ✅ ALL PASSED")
    else:
        for f in report.missing_required:
            lines.append(f"- ❌ {f}")
        for f in report.gate_failures:
            lines.append(f"- ❌ {f}")
    return "\n".join(lines)


def render_json(report: CoverageReport) -> str:
    return json.dumps({
        "total_inventory": report.total_inventory,
        "inventory_required_min": report.inventory_required_min,
        "macro_inventory_count": report.macro_inventory_count,
        "macro_inventory_ratio": report.macro_inventory_ratio,
        "covered_by_fill_rate": report.covered_by_fill_rate,
        "coverage_rate": report.coverage_rate,
        "drafts_scanned": report.drafts_scanned,
        "uncovered_inventory": [
            {"id": x.id, "type": x.type, "name": x.name, "file": x.file, "line": x.line}
            for x in report.uncovered
        ],
        "questions_total": report.questions_total,
        "questions_open": report.questions_open,
        "open_question_ratio": report.open_question_ratio,
        "integrity_issues": report.integrity_issues,
        "naming_warnings": report.naming_warnings,
        "missing_required": report.missing_required,
        "chapter_metrics": [
            {
                "file": m.file,
                "total_lines": m.total_lines,
                "body_lines": m.body_lines,
                "refs": m.refs,
                "code_blocks": m.code_blocks,
                "mermaid_blocks": m.mermaid_blocks,
                "sources_read_count": m.sources_read_count,
                "failures": m.failures,
            }
            for m in report.chapter_metrics
        ],
        "mece_total": report.mece_total,
        "mece_covered": report.mece_covered,
        "mece_excluded": report.mece_excluded,
        "mece_uncovered": report.mece_uncovered,
        "mece_coverage_rate": report.mece_coverage_rate,
        "gate_failures": report.gate_failures,
    }, ensure_ascii=False, indent=2)


# ----------------------------------------------------------------------------
# main
# ----------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description="cc-rsg Phase 4 verification")
    p.add_argument("--cc-rsg-dir", type=Path, default=Path.cwd() / ".cc-rsg")
    p.add_argument("--target-dir-for-required", default="final", choices=["drafts", "final"])
    p.add_argument("--output-format", choices=["text", "json"], default="text")

    # 章閾値
    p.add_argument("--min-refs-per-chapter", type=int, default=10)
    p.add_argument("--min-lines-per-chapter", type=int, default=200)
    p.add_argument("--min-code-blocks-per-chapter", type=int, default=3)
    p.add_argument("--min-mermaid-per-chapter", type=int, default=1)
    p.add_argument("--min-sources-read-per-chapter", type=int, default=5)

    # inventory / questions / MECE
    p.add_argument("--min-inventory", default="auto",
                   help='件数の最低値。"auto" で max(50, files_scanned/20) を計算')
    p.add_argument("--max-macro-ratio", type=float, default=0.2)
    p.add_argument("--min-questions", type=int, default=10)
    p.add_argument("--max-open-ratio", type=float, default=0.2)
    p.add_argument("--min-covered-by-fill", type=float, default=0.9)
    p.add_argument("--min-mece-coverage", type=float, default=0.7)

    # 旧版互換
    p.add_argument("--fail-on-uncovered", action="store_true")
    p.add_argument("--strict", action="store_true")

    args = p.parse_args()

    try:
        report = build_report(
            args.cc_rsg_dir,
            target_dir_name=args.target_dir_for_required,
            min_inventory=args.min_inventory,
            max_macro_ratio=args.max_macro_ratio,
            min_questions=args.min_questions,
            max_open_ratio=args.max_open_ratio,
            min_covered_by_fill=args.min_covered_by_fill,
            min_refs_per_chapter=args.min_refs_per_chapter,
            min_lines_per_chapter=args.min_lines_per_chapter,
            min_code_blocks_per_chapter=args.min_code_blocks_per_chapter,
            min_mermaid_per_chapter=args.min_mermaid_per_chapter,
            min_sources_read_per_chapter=args.min_sources_read_per_chapter,
            min_mece_coverage=args.min_mece_coverage,
        )
    except FileNotFoundError as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 2

    if args.output_format == "json":
        print(render_json(report))
    else:
        print(render_text(report))

    # 必須ファイル欠落・ゲート failure は exit 1
    if report.missing_required:
        return 1
    if report.gate_failures:
        return 1
    if args.fail_on_uncovered and report.uncovered:
        return 1
    if args.strict and report.naming_warnings:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

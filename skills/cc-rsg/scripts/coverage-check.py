#!/usr/bin/env python3
"""
cc-rsg coverage-check.py

Verification script for Phase 4 (Verify). Checks not only inventory
mentions but also per-chapter quality metrics (REF count, body line
count, code-block count, Mermaid count, Sources Read section, etc.),
Question Bank integrity, MECE coverage, and outline-mode entity
enumeration in a single pass.

Checks performed:

1.  `[REF: path:start-end]` count per chapter (`--min-refs-per-chapter`)
2.  Body-line count per chapter (`--min-lines-per-chapter`)
3.  Fenced-code-block count per chapter (`--min-code-blocks-per-chapter`)
4.  Mermaid-diagram count per chapter (`--min-mermaid-per-chapter`)
5.  Number of files under the `## Sources Read` section of each chapter (`--min-sources-read-per-chapter`)
6.  Auto-derived minimum inventory size = max(50, file_count // 20)  (`--min-inventory`)
7.  Upper bound on the ratio of grouping-style INVs like controller_group (`--max-macro-ratio`)
8.  Total `questions.json` count (`--min-questions`)
9.  Upper bound on the `status: open` ratio after Phase 5 (`--max-open-ratio`)
10. inventory.covered_by fill rate (`--min-covered-by-fill`)
11. MECE check (consults `.cc-rsg/trace.json`, `--min-mece-coverage`)
12. **User-custom deliverables**: every filename in
    `goal.json.user_custom_deliverables` must exist in the target directory
    AND have a non-empty body (>= 10 non-blank lines outside code fences).
    These files are exempt from checks 1-5 (the per-chapter comprehensive
    quality gates) because their quality bar is the user's intent expressed
    in `free_text_notes`, not the source-code-spec-chapter gates. Only
    existence + body presence is enforced.

`--fail-on-uncovered` `--strict` `--output-format` remain for backward
compatibility. Every quality check returns exit 1 on failure. All thresholds
are overridable via CLI flags.

Usage:
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
    0 = all checks PASS
    1 = one or more checks FAILED
    2 = required file (e.g. inventory.json) could not be loaded
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
# Chapter-file naming convention
# ----------------------------------------------------------------------------

NAMING_PATTERN = re.compile(r"^(0\d|[1-9]\d)-[a-z0-9-]+\.md$")
USER_CUSTOM_NAMING_PATTERN = re.compile(r"^[a-z][a-z0-9_-]*\.md$")
NAMING_EXEMPT = {"traceability.md", "README.md"}
REQUIRED_FILES = ("00-metadata.md", "99-unresolved.md", "traceability.md")

# Regexes used in chapter bodies
REF_RE = re.compile(r"\[REF:\s*([^:\]]+):(\d+)(?:-(\d+))?\]")
CODE_FENCE_RE = re.compile(r"^```([a-zA-Z0-9_-]+)?")
MERMAID_FENCE_RE = re.compile(r"^```mermaid\b")
SOURCES_READ_RE = re.compile(r"^##+\s*Sources\s*Read\b", re.IGNORECASE)
SOURCES_READ_ITEM_RE = re.compile(r"^\s*[-*]\s+`?([^`\n]+?)`?(?:\s*\([^)]*\))?\s*$")

# Keywords that make an INV count as "macro" (matched against the `type` field)
MACRO_TYPE_KEYWORDS = ("group", "module", "domain", "category", "bundle", "section")


# ----------------------------------------------------------------------------
# Data classes
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
    # backward compatibility
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
    # extended fields
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
    # outline / interactive support
    depth_mode: str = "comprehensive"
    confidence_verified: int = 0
    confidence_inferred: int = 0
    confidence_assumed: int = 0
    # user-custom deliverables (intent-vs-delivery audit, check 12)
    user_custom_expected: list[str] = field(default_factory=list)
    user_custom_failures: list[str] = field(default_factory=list)


# ----------------------------------------------------------------------------
# Loaders
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
    """Return the total file count from source-map.json if available (used by min-inventory auto)."""
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


def load_user_custom_deliverables(cc_rsg_dir: Path) -> list[str]:
    """Read `goal.json.user_custom_deliverables` if present; return [] otherwise.

    These are extra filenames the user explicitly requested in `free_text_notes`
    during Phase 0. They are exempt from the standard chapter-naming regex and
    must exist in the target directory at Phase 6 (intent-vs-delivery audit).
    Per-chapter comprehensive quality gates (200 lines / 10 REFs / Mermaid /
    Sources Read) are NOT applied to these files; only existence + non-empty
    body (check 12) is enforced.
    """
    g = cc_rsg_dir / "goal.json"
    if not g.exists():
        return []
    try:
        data = json.loads(g.read_text(encoding="utf-8"))
    except Exception:
        return []
    raw = data.get("user_custom_deliverables", [])
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        if isinstance(item, str) and USER_CUSTOM_NAMING_PATTERN.match(item):
            out.append(item)
    return out


def scan_chapter_files(target_dir: Path) -> dict[str, str]:
    """Return a `name → content` map of the .md files directly under the target directory."""
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
# Chapter-metric computation
# ----------------------------------------------------------------------------

def compute_chapter_metrics(name: str, content: str) -> ChapterMetrics:
    raw_lines = content.splitlines()
    total = len(raw_lines)

    # Body lines = lines excluding blanks, code fences, and auto-generated comments.
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
        if SOURCES_READ_RE.match(line):
            in_sources_read = True
            continue
        if in_sources_read:
            # Blank lines do NOT end the section. Standard Markdown puts a blank
            # line between the `## Sources Read` heading and its bullet list, so
            # terminating on the first blank line would zero the count for every
            # well-formatted chapter.
            if not stripped:
                continue
            if SOURCES_READ_ITEM_RE.match(line):
                sources_read_count += 1
                continue
            # Any other non-blank line (typically the next heading) ends the
            # section; fall through so it is still counted as body content.
            in_sources_read = False
        if not stripped:
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
    """Populate `failures` on each ChapterMetrics (per-chapter threshold violations)."""
    skipped_files = {"00-metadata.md", "99-unresolved.md", "traceability.md", "README.md"}
    for m in metrics:
        if m.file in skipped_files:
            continue
        if m.refs < min_refs:
            m.failures.append(f"[REF:] count is {m.refs} < required {min_refs}")
        if m.body_lines < min_lines:
            m.failures.append(f"body lines {m.body_lines} < required {min_lines}")
        if m.code_blocks < min_code_blocks:
            m.failures.append(f"code blocks {m.code_blocks} < required {min_code_blocks}")
        if m.mermaid_blocks < min_mermaid:
            m.failures.append(f"Mermaid diagrams {m.mermaid_blocks} < required {min_mermaid}")
        if m.sources_read_count < min_sources_read:
            m.failures.append(
                f"Sources Read items {m.sources_read_count} < required {min_sources_read}"
            )


# ----------------------------------------------------------------------------
# Existing logic (macro ratio, naming, INV mention check, etc.)
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
            issues.append(f"{qid}: missing required fields: {sorted(missing)}")
        sev = q.get("severity")
        if sev and sev not in valid_severities:
            issues.append(f"{qid}: invalid severity value: {sev}")
        st = q.get("status")
        if st and st not in valid_statuses:
            issues.append(f"{qid}: invalid status value: {st}")
        if st == "answered":
            if not q.get("answer"):
                issues.append(f"{qid}: status=answered but `answer` is empty")
        related_inv = q.get("related_inventory_ids", []) or []
        for inv_id in related_inv:
            if inv_id not in inventory_ids:
                issues.append(
                    f"{qid}: related_inventory_ids entry {inv_id} not found in inventory.json"
                )

    blocked_pattern = re.compile(r"\[BLOCKED:\s*see\s+(Q-[A-Za-z0-9_-]+)\]")
    blocked_referenced: list[str] = []
    for content in drafts.values():
        for match in blocked_pattern.finditer(content):
            ref_id = match.group(1)
            if ref_id not in question_ids:
                issues.append(f"draft contains [BLOCKED: see {ref_id}] but the question is missing from questions.json")
            else:
                blocked_referenced.append(ref_id)

    return issues, sorted(set(blocked_referenced))


def check_naming_convention(drafts_dir: Path, user_custom: list[str] | None = None) -> list[str]:
    """Flag files that violate the chapter-naming regex.

    `user_custom` extends `NAMING_EXEMPT` dynamically; entries listed in
    `goal.json.user_custom_deliverables` are NOT counted as naming violations.
    """
    if not drafts_dir.exists() or not drafts_dir.is_dir():
        return []
    allowed_exempt = set(NAMING_EXEMPT) | set(user_custom or [])
    warnings: list[str] = []
    for f in sorted(drafts_dir.glob("*.md")):
        if f.name in allowed_exempt:
            continue
        if not NAMING_PATTERN.match(f.name):
            warnings.append(
                f"{f.name} violates the naming convention ({NAMING_PATTERN.pattern}) and is not in the reserved list {sorted(NAMING_EXEMPT)} or the user_custom_deliverables list"
            )
    return warnings


def check_user_custom_deliverables(target_dir: Path, user_custom: list[str], min_body_lines: int = 10) -> list[str]:
    """Verify every user-custom deliverable exists in the target dir with a non-empty body.

    "Non-empty body" means at least `min_body_lines` non-blank lines outside
    of code fences. This catches the case where the agent stubs the file but
    never fills it.

    Per-chapter comprehensive quality gates (200 lines, REFs, Mermaid, etc.)
    do NOT apply to user_custom files — those are handled by the caller via
    explicit exclusion from `evaluate_chapter_gates`. Only existence + body
    presence is enforced here (check 12).
    """
    failures: list[str] = []
    if not user_custom:
        return failures
    if not target_dir.exists():
        return [f"target directory {target_dir} does not exist (cannot verify user-custom deliverables)"]
    for name in user_custom:
        p = target_dir / name
        if not p.exists():
            failures.append(f"user-custom deliverable {name} is missing from {target_dir}")
            continue
        try:
            content = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = p.read_text(encoding="utf-8", errors="replace")
        in_code = False
        body_lines = 0
        for line in content.splitlines():
            if CODE_FENCE_RE.match(line):
                in_code = not in_code
                continue
            if in_code:
                continue
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("<!--") or stripped.startswith("-->"):
                continue
            body_lines += 1
        if body_lines < min_body_lines:
            failures.append(
                f"user-custom deliverable {name} exists but body has only {body_lines} non-blank lines (need >= {min_body_lines})"
            )
    return failures


def check_required_files(target_dir: Path) -> list[str]:
    missing: list[str] = []
    if not target_dir.exists():
        return [f"target directory {target_dir} does not exist"]
    for required in REQUIRED_FILES:
        if not (target_dir / required).exists():
            missing.append(f"required file {required} is missing from {target_dir}")
    return missing


# ----------------------------------------------------------------------------
# Report construction
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

    # backward compatibility: mention detection
    uncovered: list[InventoryItem] = []
    for item in inventory:
        # Use any existing covered_by values (set by the agent if filled manually).
        if not item.covered_by:
            item.covered_by = detect_mentions(item, chapters)
        if not item.covered_by:
            uncovered.append(item)

    integrity_issues, blocked_referenced = check_question_integrity(
        questions, inventory_ids, chapters
    )

    user_custom = load_user_custom_deliverables(cc_rsg_dir)
    naming_warnings = check_naming_convention(target_dir, user_custom=user_custom)
    missing_required = check_required_files(target_dir)
    user_custom_failures = check_user_custom_deliverables(target_dir, user_custom)

    # Chapter metrics
    chapter_metrics: list[ChapterMetrics] = []
    for name, content in chapters.items():
        chapter_metrics.append(compute_chapter_metrics(name, content))

    # user_custom chapters are evaluated only by check 12 (existence + non-empty body).
    # The comprehensive per-chapter gates (200 lines / 10 REFs / code blocks / Mermaid /
    # Sources Read) are designed for source-derived spec chapters, not for user-narrated
    # files like manual.md. Split chapter_metrics into "standard" and "user_custom" so
    # only the standard ones receive evaluate_chapter_gates.
    user_custom_set = set(user_custom)
    standard_chapter_metrics = [m for m in chapter_metrics if m.file not in user_custom_set]

    # In outline / interactive mode the comprehensive-mode chapter gates
    # (200 lines / 10 REFs / code blocks / Mermaid / 5 Sources Read) are
    # dropped. Instead, the MECE criterion is "every entity appears in
    # some row of some table" — reuse the uncovered logic below.
    if depth_mode == "comprehensive":
        evaluate_chapter_gates(
            standard_chapter_metrics,
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

    # Macro ratio
    macro_count = sum(1 for it in inventory if is_macro_type(it))
    macro_ratio = (macro_count / len(inventory)) if inventory else 0.0

    # covered_by fill rate
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

    # Gate evaluation
    gate_failures: list[str] = []
    if len(inventory) < required_min:
        gate_failures.append(
            f"inventory.json size {len(inventory)} < required {required_min} "
            f"(may be under-granular for the codebase size)"
        )
    if macro_ratio > max_macro_ratio:
        gate_failures.append(
            f"macro-type INV ratio {macro_ratio:.1%} > cap {max_macro_ratio:.1%} "
            f"({macro_count}/{len(inventory)} are group/module-style — please subdivide)"
        )
    if covered_by_fill_rate < min_covered_by_fill:
        gate_failures.append(
            f"inventory.covered_by fill rate {covered_by_fill_rate:.1%} < {min_covered_by_fill:.1%}"
        )
    if len(questions) < min_questions:
        gate_failures.append(
            f"questions.json size {len(questions)} < required {min_questions} "
            f"(raise more questions for Phase 5 dialogue)"
        )
    if questions and open_ratio > max_open_ratio:
        gate_failures.append(
            f"open-status ratio {open_ratio:.1%} > cap {max_open_ratio:.1%} "
            f"(complete the Phase 5 three-stage dialogue)"
        )
    if trace is not None and mece_rate < min_mece_coverage:
        gate_failures.append(
            f"MECE coverage {mece_rate:.1%} < {min_mece_coverage:.1%} "
            f"(uncovered={mece_uncovered}/{mece_total - mece_excluded})"
        )
    if trace is None:
        gate_failures.append(
            "trace.json missing. Run build-trace.py to enable the MECE check."
        )

    # Reflect per-chapter metric failures into the overall gate failures.
    # (user_custom chapters were excluded from evaluate_chapter_gates above; their
    # m.failures is empty even if 200-line / 10-REF gates would have failed.)
    for m in chapter_metrics:
        if m.failures:
            for f in m.failures:
                gate_failures.append(f"chapter {m.file}: {f}")

    # Reflect user-custom deliverable failures (Phase 6 intent-vs-delivery gate, check 12).
    for f in user_custom_failures:
        gate_failures.append(f"user_custom: {f}")

    # Aggregate confidence labels for outline / interactive mode.
    # Count how many times 🟢 VERIFIED / 🟡 INFERRED / 🔴 ASSUMED appear in chapter bodies.
    verified = inferred = assumed = 0
    if depth_mode != "comprehensive":
        for _, content in chapters.items():
            verified += content.count("🟢") + content.count("VERIFIED")
            inferred += content.count("🟡") + content.count("INFERRED")
            assumed  += content.count("🔴") + content.count("ASSUMED")
        # Warn if the ASSUMED ratio is too high.
        total_labels = verified + inferred + assumed
        if total_labels > 0:
            assumed_ratio = assumed / total_labels
            if assumed_ratio > 0.6:
                gate_failures.append(
                    f"[outline] ASSUMED ratio is {assumed_ratio:.0%} "
                    f"(over 60%) — strengthen grounding via mechanical extraction"
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
        user_custom_expected=user_custom,
        user_custom_failures=user_custom_failures,
    )


# ----------------------------------------------------------------------------
# Rendering
# ----------------------------------------------------------------------------

def render_text(report: CoverageReport) -> str:
    lines: list[str] = []
    lines.append("=== cc-rsg Phase 4 verification report (v2) ===")
    lines.append("")
    lines.append(f"[Depth mode] {report.depth_mode}")
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
            lines.append("  Confidence KPI: no labels detected — attach 🟢/🟡/🔴 to each table cell")
    lines.append("")
    lines.append("[Inventory coverage]")
    lines.append(f"- Total inventory items: {report.total_inventory} (required minimum: {report.inventory_required_min})")
    lines.append(f"- Mentioned: {report.covered} ({report.coverage_rate:.1f}%)")
    lines.append(f"- Unmentioned: {len(report.uncovered)}")
    lines.append(f"- Macro type: {report.macro_inventory_count} ({report.macro_inventory_ratio:.1%})")
    lines.append(f"- covered_by fill rate: {report.covered_by_fill_rate:.1%}")
    lines.append("")
    lines.append("[MECE check]")
    if report.mece_total > 0:
        lines.append(f"- Total source units: {report.mece_total}")
        lines.append(f"- Covered by the spec: {report.mece_covered} ({report.mece_coverage_rate:.1%})")
        lines.append(f"- Explicitly excluded: {report.mece_excluded}")
        lines.append(f"- Uncovered: {report.mece_uncovered}")
    else:
        lines.append("- trace.json missing; MECE check not performed")
    lines.append("")
    lines.append("[Question Bank]")
    lines.append(f"- Total: {report.questions_total}")
    lines.append(f"- Open remaining: {report.questions_open} ({report.open_question_ratio:.1%})")
    lines.append("")
    lines.append("[Per-chapter quality metrics]")
    for m in report.chapter_metrics:
        flag = "❌" if m.failures else "✅"
        lines.append(
            f"  {flag} {m.file}: body={m.body_lines} lines, refs={m.refs} "
            f"code={m.code_blocks} mermaid={m.mermaid_blocks} sources_read={m.sources_read_count}"
        )
        for f in m.failures:
            lines.append(f"      - {f}")
    if report.user_custom_expected:
        lines.append("")
        lines.append(f"[User-custom deliverables expected from goal.json: {len(report.user_custom_expected)}]")
        for name in report.user_custom_expected:
            flag = "✅" if not any(name in f for f in report.user_custom_failures) else "❌"
            lines.append(f"  {flag} {name}")
    lines.append("")
    lines.append("[Gate decision]")
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
        "user_custom_expected": report.user_custom_expected,
        "user_custom_failures": report.user_custom_failures,
        "gate_failures": report.gate_failures,
    }, ensure_ascii=False, indent=2)


# ----------------------------------------------------------------------------
# main
# ----------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description="cc-rsg Phase 4 verification (v2)")
    p.add_argument("--cc-rsg-dir", type=Path, default=Path.cwd() / ".cc-rsg")
    p.add_argument("--target-dir-for-required", default="final", choices=["drafts", "final"])
    p.add_argument("--output-format", choices=["text", "json"], default="text")

    # Per-chapter thresholds
    p.add_argument("--min-refs-per-chapter", type=int, default=10)
    p.add_argument("--min-lines-per-chapter", type=int, default=200)
    p.add_argument("--min-code-blocks-per-chapter", type=int, default=3)
    p.add_argument("--min-mermaid-per-chapter", type=int, default=1)
    p.add_argument("--min-sources-read-per-chapter", type=int, default=5)

    # inventory / questions / MECE
    p.add_argument("--min-inventory", default="auto",
                   help='Minimum item count. With "auto", compute max(50, files_scanned/20).')
    p.add_argument("--max-macro-ratio", type=float, default=0.2)
    p.add_argument("--min-questions", type=int, default=10)
    p.add_argument("--max-open-ratio", type=float, default=0.2)
    p.add_argument("--min-covered-by-fill", type=float, default=0.9)
    p.add_argument("--min-mece-coverage", type=float, default=0.7)

    # backward compatibility
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
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    if args.output_format == "json":
        print(render_json(report))
    else:
        print(render_text(report))

    # Missing required files or any gate failure → exit 1.
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

---
name: cc-rsg
description: Reverse-engineer comprehensive specification documents from existing codebases through goal-driven reconnaissance, WBS-based parallel investigation, and iterative question-bank dialogue.
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, Task, AskUserQuestion, WebFetch, WebSearch
---

# cc-rsg (Claude Code Reverse Spec Generator)

A general-purpose framework that reverse-engineers maintenance- or delivery-targeted specification documents from existing codebases (legacy or current).

This skill operates in the "code → spec" direction; it is the symmetric counterpart of `cc-sdd` (Spec Driven Development). Both belong to the same family of tools.

> **🌐 Language policy: English is the base language; Japanese is opt-in.**
>
> The default for `goal.json.output_language` is `"en"` (or the user's
> UI-language hint passed from the cc-rsg-web harness). Phase 0 MUST ask
> the user to confirm. After Phase 0, **all deliverables follow
> `output_language`**: en (default) → English; ja → Japanese.
>
> Internal markers, JSON keys, file names (ASCII slug), `[REF: ...]`,
> `[CONFIDENCE: ...]`, enum values, and the literal heading `## Sources Read`
> stay **English forever** regardless of `output_language`. `templates/` and
> `references/` are also being migrated to English; until that work
> completes, when `output_language == "ja"` the agent translates rendered
> output into Japanese while preserving the structure, IDs, REF markers,
> and JSON keys verbatim.

---

## Design principles

This skill operates under the following 11 principles. They are mutually reinforcing; if any one breaks, the reliability of the whole skill collapses.

1. **Goal-driven**: Phase 0 fixes the goal through a 5-question choice-based dialogue and persists it to `.cc-rsg/goal.json`. All subsequent phases reference this goal.
2. **Hybrid template decision**: Supports three template sources — the user's own template, a Claude-recommended template (derived from reconnaissance), or a user-adjusted version of the recommendation.
3. **Reference-based inventory unit selection**: `references/inventory-units.md` lists typical units per language/framework; the relevant patterns for the target codebase are chosen from there.
4. **Gap-prevention is anchored on inventory-based verification**: Enumerate every extractable unit from the code and mechanically check whether the spec covers each one.
5. **Question Bank is populated at 3 moments**: end of reconnaissance (high-level questions), during sub-agent investigation (detail questions), and at verification (consistency questions). Classified into 7 standard categories.
6. **Sub-agents decide dynamically based on question severity**: Critical → leave the section blocked. Important / nice-to-have → proceed with an inference, leaving a marker.
7. **Question merge is automatic only for "obviously identical"**: "Similar but subtly different" questions are grouped and surfaced to the user for judgement.
8. **The dialogue protocol is Claude-driven**: Choice-based questions are the default; free-form input is a fallback. AskUserQuestion-style choice UIs are exploited to the maximum.
9. **Unanswerable questions are marked `abandoned`**: They are explicitly recorded in the final spec under "unresolved items", never hidden.
10. **Dual-consumer handling is reduced to one in goal definition**: If multiple views are needed, restart instead of overloading a single spec.
11. **Output language is chosen in Phase 0 (English / 日本語) — English is the BASE language as of 2026-06**: The very first dialogue is bilingual (English first, then Japanese). The default selection is provided by the upstream cc-rsg-web initial prompt (the user's UI-language hint; falls back to `"en"`). The answer is persisted to `.cc-rsg/goal.json` as `output_language` (`"en"` or `"ja"`). All subsequent natural-language output — AskUserQuestion bodies and choices, progress messages, confirmation summaries, generated spec body and chapter titles, `questions.json` `body` / `answer`, Phase 4 verification reports, resume messages — uses that language. Internal identifiers and machine-readable elements — state keys (`current_phase` etc.), IDs (`Q-XXX` / `INV-XXX`), file names (ASCII slug), `[REF: file:lines]`, `[CONFIDENCE: HIGH|MED|LOW]`, `[ASK SME]`, `[ASSUMED: ...]`, `[BLOCKED: ...]` marker names, and `goal.json` enum values (`primary_reader: "maintenance_developer"` etc.) — stay English **regardless of `output_language`**. The literal `## Sources Read` heading also stays English (so `coverage-check.py` pattern-matches it). The skill body (this SKILL.md plus `agents/` and `variants/`) is English. `templates/*.md` and `references/*.md` are being migrated in follow-up phases; while they remain partially Japanese, the agent dynamically translates rendered output to English when `output_language == "en"`, preserving the structure verbatim.

---

## 6-phase state machine overview

The skill is implemented as a 6-phase state machine. Progress is tracked in `.cc-rsg/state.json` and is pause-and-resume safe.

| Phase | Name | Main deliverables |
|-------|------|------------|
| 0 | Setup & Goal | `.cc-rsg/goal.json` |
| 1 | Recon & Template | `recon-report.md`, template selection result |
| 2 | Plan & WBS | `inventory.json`, `wbs.json` |
| 3 | Investigate | `drafts/*.md` (per-chapter drafts) |
| 4 | Verify | coverage report, consistency questions |
| 5 | Refine via Dialogue | resolved `questions.json` |
| 6 | Deliver | final spec under `final/` |

Each phase is defined in detail in the sections below.

---

## Phase 0: Setup & Goal

### Purpose
Right after the skill starts, fix the scope and the goal. Every later decision derives from the goal defined here.

### Procedure

1. **Project confirmation**
   - Start from the current working directory and identify the target project.
   - Ask the user "Is this the right root directory for the target codebase?". If not, obtain the correct path.

2. **Initialize the state directory**
   - Create the `.cc-rsg/` directory.
   - If an existing `.cc-rsg/state.json` is found, branch to resume mode (see "State management and resume" below).

3. **Output language selection**

   - **This step alone is presented bilingually** because the user's preferred language has not yet been confirmed. The question body and choice labels appear in both English and Japanese.
   - Use `AskUserQuestion` with:
     - Question: `Select the output language for the dialogue and the generated specs / 対話と生成ドキュメントの出力言語を選択してください`
     - Choices (**fixed order; English is the default**):
       1. `English`
       2. `日本語 (Japanese)`
     - `allow_multiple = false`, `allow_free_text = false`
   - Map the selected label to `output_language`: `English` → `"en"`, `日本語 (Japanese)` → `"ja"`. Persistence to `goal.json` happens together with the other answers in Step 5.
   - **Default policy (English-base, effective 2026-06)**: when the user submits without changing the highlighted choice, treat the answer as `"en"`. This matches the cc-rsg upstream policy.
   - **cc-rsg-web hint precedence**: when the parent harness (cc-rsg-web) injects a `userUiLanguage` hint into the initial prompt (see `src/lib/openhands.ts` "Language policy" block), use that hint to decide which choice is **pre-highlighted** (`en` highlights `English`; `ja` highlights `日本語 (Japanese)`). The hint never overrides the user's explicit selection. Priority order:
     1. The user's explicit click in this step (highest)
     2. `userUiLanguage` hint passed from cc-rsg-web initial prompt
     3. Hard default `"en"` (lowest)
   - **All natural-language output from Step 4 onward** — `AskUserQuestion` bodies and choices, confirmation summaries, chapter titles, generated spec body, `questions.json` body text, etc. — is rendered in the language selected here (see Design Principle #11).
   - **Resume mode**: when `.cc-rsg/goal.json` already exists, read the persisted `output_language` and skip this step entirely.

4. **Run the 5 goal-definition questions**
   - Use `AskUserQuestion` to ask the following 5 questions in sequence. **Question bodies, choice labels, and free-form-input placeholders are all rendered in the `output_language` selected in Step 3.** The choice labels below are shown when `output_language == "en"`; the agent dynamically translates them when `output_language == "ja"` (enum values such as `primary_reader: "maintenance_developer"` stay as language-independent English enums in `goal.json`). Each question is choice-based first with a free-form field as a fallback.

   **Q1. Who is the primary reader of the spec?**
   - Maintenance developer
   - Delivery customer
   - SME (subject-matter expert)
   - Regulator
   - Other (free-form)

   **Q2. What will the reader do after reading the spec?**
   - Code change
   - Approval decision
   - Audit
   - Learning
   - Other (free-form)

   **Q3. What level of granularity is preferred?**
   - High-level overview
   - Medium
   - Detailed
   - Other (free-form)

   **Q4. Which perspectives should be emphasised? (multi-select)**
   - Functional correctness
   - Business validity
   - Security
   - Operability
   - Performance
   - Other (free-form)

   **Q5. What about existing documentation?**
   - No existing docs
   - Existing docs / want to update
   - Existing docs / want to coexist
   - Existing docs / want to retire
   - Other (free-form)

5. **Persist to `goal.json`**
   - Save the language choice from Step 3 and the 5 answers from Step 4 as a structured `goal.json` under `.cc-rsg/`. Schema:

   ```json
   {
     "output_language": "en",
     "primary_reader": "maintenance_developer",
     "reader_action": "code_change",
     "granularity": "medium",
     "perspectives": ["functional_correctness", "operational"],
     "existing_docs": "none",
     "free_text_notes": "..."
   }
   ```
   - `output_language` is required and must be `"en"` or `"ja"`. Other enum fields (`primary_reader`, `reader_action`, `granularity`, `perspectives`, `existing_docs`) are language-independent English enums (localized only at display time using `output_language`).

6. **Phase 0 complete**
   - Update `state.json` and proceed to Phase 1.

### Phase-specific cautions
- Minimise the user's burden by leading with choice-based UI; never force the user to type the same thing twice.
- Treat the free-form field as a "none of the above" safety net; it is unnecessary when the user picked one of the choices.
- The goal influences every later phase, so do not skip summarising the answers and asking the user to confirm. **The confirmation summary is also rendered in `output_language`.**
- The output-language selection (Step 3) is **bilingual only for that first dialogue**. From Step 4 on, use the confirmed language exclusively. If the user requests a language switch mid-flight, update `goal.json.output_language` and individually check whether existing `drafts/` and `questions.json` bodies need to be re-rendered.

---

## Phase 1: Recon & Template

### Purpose
Get a rough mental model of the codebase via a shallow reconnaissance, then pick an appropriate spec template. At the end of Phase 1, register the high-level questions into the Question Bank.

### Procedure

1. **Run the shallow reconnaissance**
   Read the following and summarise them in `recon-report.md`:
   - File tree structure (limited to depth 3-4, noise excluded)
   - Package-manager files (`package.json`, `composer.json`, `requirements.txt`, `pom.xml`, `build.gradle`, etc.)
   - Entry-point candidates (`main` functions, `index` files, routing definitions, etc.)
   - Existing documentation (`README.md`, `docs/`, `wiki`, etc.)
   - Build/deploy configuration (`Dockerfile`, `Makefile`, CI configs, etc.)
   - Language mix and estimated line counts

2. **Present template candidates**
   - Consult `references/template-catalog.md` and propose candidates suitable for the target codebase.
   - Use `AskUserQuestion` to present the candidates to the user.

   **Example template choices**:
   - I have my own template (specify path)
   - Web application spec (`templates/web-app.md`)
   - Batch processing system spec (`templates/batch-system.md`)
   - API service spec (`templates/api-service.md`)
   - Library/SDK spec (`templates/library-sdk.md`)
   - Use whichever Claude recommends from reconnaissance

3. **Adjust the chosen template**
   - If the user accepts Claude's recommendation, display the chapter outline and ask "Are there chapters to add, remove, or rename?".
   - Reflect any additions/removals.

4. **Register high-level questions**
   - Add the fundamental questions surfaced during reconnaissance (questions that block big-picture understanding) into `questions.json`.
   - Examples:
     - What business problem is this system trying to solve?
     - How wide is the scope (which module inside the monorepo)?
     - When existing docs disagree with the code, which is authoritative?
   - See "Question Bank operation" below for the structure used at registration.

5. **🆕 depth-mode decision (scale-based)**
   - Record the **total file count** observed during reconnaissance at the top of `recon-report.md`. Persist as `total_files` in `.cc-rsg/state.json`.
   - **If file count > 200**, ask the user with `AskUserQuestion` to choose a **depth mode**:
     - `comprehensive`: classic behaviour. All chapters detailed, full MECE, full REFs. **Recommended only when exhaustive coverage is required (audit, regulatory).** Takes hours to days.
     - `outline` (**recommended default**): each level's entities are **listed exhaustively in tables** + Mermaid diagrams + a "deep-dive candidates" list at the end of each table. Details are produced on-demand in dialogue after Phase 6. **Best for typical use.**
     - `interactive`: same flow as outline, plus continued deep-dive acceptance after Phase 6 completes. **Use when a team will continue referencing the spec.**
   - **If file count ≤ 200**, default to `comprehensive` automatically (no question). The user may still override.
   - Persist the result to `.cc-rsg/goal.json` as `depth_mode: "comprehensive" | "outline" | "interactive"`. Phases 2 / 3 / 4 / 6 branch on this value.
   - Question wording example:
     > The target codebase is large (N files / X lines). Choose a depth mode for the spec.
     > (Overview-only → deep-dive items of interest later, in practice, is recommended.)

6. **Phase 1 complete**
   - Update `state.json` and proceed to Phase 2.

### Phase-specific cautions
- Reconnaissance follows the principle "shallow but wide". Detailed logic understanding is deferred to Phase 3.
- Without noise exclusion (`node_modules`, `vendor`, `.git`, etc.) the output explodes.
- If the user brings their own template, you may point out "Claude's recommendation differs", but the decision is the user's.

---

## Phase 2: Plan & WBS

### Purpose
Finalise the skeleton of the spec, decompose the work to fill each chapter into a WBS of sub-tasks, and extract the inventory into `inventory.json`.

### Procedure

1. **Apply the chapter file naming convention and generate the skeleton**
   - Every chapter file follows the convention below. Free naming by Claude is forbidden.
     - **File name**: `{NN}-{slug}.md`
       - `NN`: zero-padded two-digit chapter number (`00`-`99`)
       - `slug`: ASCII lowercase + digits + hyphens only (e.g. `01-overview.md`, `04-oauth-oidc.md`)
       - Strict regex: `^(0\d|[1-9]\d)-[a-z0-9-]+\.md$`
     - **Chapter title in body**: handled independently of the file name. Rendered in `goal.json.output_language` (EN example: `# Chapter 1: Overview` / JA example: `# 第1章: 概要`).
     - **Chapter numbers are assigned by the main agent in Phase 2** and fixed in `wbs.json.chapters[].file_name`. Sub-agents never decide naming; they save under the file name handed down by the main agent.
   - **Reserved numbers / file names** (must always be generated):
     - `00-metadata.md` (metadata chapter)
     - `99-unresolved.md` (unresolved-items chapter)
     - `traceability.md` (traceability table, no chapter number)
   - Regular chapter numbers are assigned sequentially in `01`-`98` while avoiding collisions with reserved numbers.
   - **When to generate them**: at Phase 2, create empty chapter files under `drafts/` for all chapters including the metadata, unresolved-items, and traceability chapters (the body will be filled in Phase 3 / Phase 6).
   - Place a meta comment (`<!-- meta: ... -->`) at the top of each chapter file describing what that chapter covers.
   - The skeleton of `00-metadata.md` carries a meta comment indicating "Phase 6 will write goal.json snapshot / generation timestamp / commit hash / template selection result here".
   - The skeleton of `99-unresolved.md` carries a meta comment indicating "Phase 6 will aggregate `abandoned` entries from `questions.json` here".
   - The skeleton of `traceability.md` carries a meta comment indicating "Phase 6 will write the chapter/section → source mapping table here".

2. **Create the WBS**
   - Define sub-tasks that fill each chapter. The model is "1 sub-task = 1 sub-agent".
   - Sub-task granularity: split each sub-task to "a size that preserves accuracy". Too big → coarse output; too small → overhead.
   - Save the WBS to `wbs.json`. Schema:

   ```json
   {
     "chapters": [
       {
         "chapter_id": "ch-01-overview",
         "chapter_title": "Chapter 1: Overview",
         "file_name": "01-overview.md",
         "assigned_inventory_ids": ["INV-001", "INV-002"],
         "status": "pending"
       }
     ]
   }
   ```
   <!-- chapter_title example: EN "Chapter 1: Overview" / JA "第1章: 概要" — chosen by output_language -->

   - `file_name` is required and must satisfy the regex above (`^(0\d|[1-9]\d)-[a-z0-9-]+\.md$`).
   - The three files `00-metadata.md` / `99-unresolved.md` / `traceability.md` appear in the `chapters` array but with an empty `assigned_inventory_ids` array; Phase 6 fills their bodies.

3. **Inventory extraction (v2: source-map.py based)**

   **STEP A (required)**: Run `scripts/source-map.py` to extract source units automatically:
   ```bash
   python .cc-rsg/skill/scripts/source-map.py \
     --target <target root> \
     --output .cc-rsg/source-map.json
   ```
   This enumerates language-specific classes, modules, routes, migrations, views, etc. as `SRC-NNNN`.

   **STEP B (required)**: Derive the minimum INV count from `source-map.json`'s `stats.files_scanned`:
   ```
   inventory.json minimum count = max(50, files_scanned // 20)
   ```
   Falling below this fails `coverage-check.py`.

   **STEP C**: Consulting `references/inventory-units.md`, group `source-map.json` units into conceptual units per language catalogue:
   - Examples (per language):
     - PHP: classes, traits, functions, route definitions
     - COBOL: PROGRAM-ID, SECTION, PARAGRAPH
     - Python: modules, classes, functions, endpoints
     - Java: classes, methods, endpoints, entities
     - JavaScript/TypeScript: exported functions, components, routes
     - **Ruby on Rails**: always cover the 14-item "Ruby on Rails catalogue" in `inventory-units.md` (Controller/Model/Concern/Service/Job/Mailer/Helper/Lib/Migration/Route group/View group/JS module/Config/Mailer template).

   **STEP D**: macro/group/module style types are forbidden. Always 1 class / 1 module / 1 action per row.

   Save the result to `inventory.json`. Schema:

   ```json
   {
     "units": [
       {
         "id": "INV-001",
         "type": "controller",
         "name": "IssuesController",
         "file": "redmine-master/app/controllers/issues_controller.rb",
         "line": 20,
         "covered_by": [],
         "related_source_ids": ["SRC-0142", "SRC-0143"]
       }
     ]
   }
   ```

   `related_source_ids` links to `source-map.json` units; this enables the MECE check in Phase 4.

4. **Map WBS chapters to inventory items**
   - For each inventory item, decide which chapter covers it in the WBS.

5. **🆕 Adjust the chapter structure based on depth mode (the mode confirmed in Phase 1.5)**

   Branch the WBS chapter structure on `.cc-rsg/goal.json`'s `depth_mode`:

   **(a) `comprehensive` (classic / audit use)**
   - Distribute `assigned_inventory_ids` across the 13-chapter template outline.
   - Phase 3 generates ≥ 200 lines / ≥ 10 REFs per chapter.
   - **For large repos this takes hours to days. Assumes an audit reader.**

   **(b) `outline` or `interactive` (recommended default)**
   - **Chapters are restructured to "table-first"**. Use `references/outline-tables.md` to decide per language.
   - **Required chapters (Layer 1: MECE-guaranteed)**:
     - `01-modules-overview.md` — Modules table (exhaustive responsibility partitioning)
     - `02-entities.md` — Entities table (exhaustive listing of models / structs / types / classes / interfaces)
     - `03-actions.md` — Actions table (exhaustive listing of controllers / handlers / endpoints)
     - `04-data.md` — Data table (DB schema / migrations)
     - `05-dependencies.md` — Dependencies table (gem / pip / npm, etc.)
   - **Required chapters (Layer 2: relationship visualisation)**:
     - `06-diagrams.md` — Mermaid (ER diagram, module dependency, representative sequences, state transitions)
   - **Optional chapters (as needed)**:
     - `07-flows.md` — Per-use-case sequences (multiple)
     - `08-cross-cutting.md` — Cross-cutting concerns: auth / logging / transactions, etc.
   - **Reserved chapters stay** as `00-metadata.md` / `99-unresolved.md` / `traceability.md`.
   - **Do NOT enforce the 200-line body / 10-REF requirements**. Instead, `coverage-check.py` checks that **each table enumerates every entity**.
   - Record `depth_mode` on each chapter in `wbs.json` so Phase 3 / 4 can branch on it.

6. **User review**
   - Display the WBS and the skeleton and ask the user "Is it OK to start Phase 3 with this decomposition?".
   - In outline / interactive mode, also call out that the chapters are "overview-table-first" and obtain consent.

7. **Phase 2 complete**
   - Update `state.json` and proceed to Phase 3.

### Phase-specific cautions
- Inventory extraction scripts are generated by Claude on the fly. Pre-built generic scripts cannot keep up with language-specific details.
- WBS granularity directly drives sub-agent precision. When in doubt, split finer.
- Skipping the user review causes large rework in Phase 3.
- **Strictly observe the chapter file naming convention**. Free-form names like `chapter2_architecture.md` or `第3章_認証.md` are NOT allowed. Violations are flagged by `scripts/coverage-check.py`.

---

## Phase 3: Investigate (read code, then write chapters)

### Purpose
Based on the WBS, **read the real source code first, then write each chapter**.

### 🆕 depth-mode branching (important)

`.cc-rsg/goal.json`'s `depth_mode` **changes Phase 3's overall behaviour**:

| depth_mode | Main behaviour | Chapter body shape |
|---|---|---|
| `comprehensive` | Apply STEP A-F below to every chapter | Long form: ≥ 200 lines + ≥ 10 REFs + ≥ 1 Mermaid + ≥ 5 Sources Read |
| **`outline` / `interactive`** | **STEP A-F are replaced for Layer 1 / 2 chapters** (see "outline-mode chapter writing" below) | Table-first + relationship diagrams + deep-dive candidate list |

In `outline` / `interactive` mode the following `comprehensive`-only STEPs do NOT apply:
- "200 lines or more" body length enforcement
- "10 REFs or more" citation enforcement
- "5 Sources Read or more" required count

Instead, use the **outline-mode writing rules** (below).

---

### 🚨 v2 mandatory principles (strict) — for `comprehensive` mode

To make "writing a chapter without opening the code" structurally impossible, perform each chapter in this order:

#### STEP A: Sources Read (mandatory; skipping causes Phase 4 failure)

For every INV in that chapter's `wbs.json.chapters[*].assigned_inventory_ids`, **`file_editor view` the corresponding real source files**.

List the viewed file paths and line ranges at the **top of the chapter under a `## Sources Read` section**:

```markdown
# Chapter 5: Data Model

## Sources Read
- `redmine-master/app/models/issue.rb` (lines 1-440)
- `redmine-master/app/models/project.rb` (lines 1-690)
- `redmine-master/app/models/user.rb` (lines 1-120)
- `redmine-master/db/migrate/0042_create_issues.rb` (lines 1-50)
- `redmine-master/app/models/concerns/issue_relations.rb` (lines 1-95)

## 5.1 Overview
...
```

**Minimum 5 files** under Sources Read. `coverage-check.py` enforces this count. Writing `[REF:]` citations for files that are not listed (or never `view`-ed) is forbidden.

#### STEP B: Citation extraction (mandatory)

Extract at least **10 concrete citations** from the viewed code:

```
[REF: redmine-master/app/models/issue.rb:42-56]
[REF: redmine-master/app/models/issue.rb:120-145]
...
```

Cover class definitions, key methods, configuration values, callbacks, validations, exception handling, etc. Line ranges are precise (coarse ranges like `:1-500` are not acceptable).

#### STEP C: Write the chapter body (required quality bar)

Incorporate the citations into the body. **Per-chapter mandatory requirements**:

| Item | Minimum | Verification script |
|------|---------|-------------|
| Body lines | ≥ 200 | coverage-check.py |
| `[REF:]` count | ≥ 10 | coverage-check.py |
| fenced code block | ≥ 3 | coverage-check.py |
| Mermaid diagrams | ≥ 1 | coverage-check.py |
| Sources Read items | ≥ 5 | coverage-check.py |

Chapters that fail these are rejected in Phase 4 and loop back to Phase 3 for correction.

Around each `[REF: ...]`, add prose explaining "what is happening". Writing only what Rails/Laravel-style frameworks "typically do" is forbidden — write what the **actual code** does after reading it.

#### STEP D: Uncertainty markers

Surface uncertainty in each statement:
- `[CONFIDENCE: HIGH | MED | LOW]`
- `[ASK SME]` (needs confirmation from a subject-matter expert)
- `[ASSUMED: ...]` (basis for the inference)

#### STEP E: Add detail questions to the Question Bank

Questions that surface while writing a chapter are added to `questions.json` (at least 1 per chapter). The final `questions.json` must contain **≥ 10 items** (`coverage-check.py` enforces this).

Examples:
- Is this method retrying three times because of a technical constraint or a business requirement?
- What is the rationale for this configuration value?
- Is this commented-out code a transient remnant or part of the spec?

#### STEP F: Handle critical questions

If a critical question is hit, leave the corresponding section as `[BLOCKED: see Q-042]` (empty). Loop back from Phase 5 (after dialogue) to Phase 3 to fill it in.

#### STEP G: Per-chapter sub-agent delegation (use when the `task` tool is available; recommended)

In environments where the `task` tool is available (cc-rsg-web v2 and later), **delegate each chapter to an isolated `chapter-investigator` sub-agent**. Writing every chapter directly in the main agent degrades context; investigating each chapter in its own context yields higher quality.

**Sub-agent invocation template:**

```
task(
  description="ch05 data-model investigation",
  prompt=\"\"\"
You are the chapter-investigator handling Chapter 5: Data Model.

Target inventory_ids:
- INV-012 (Project)
- INV-013 (Issue)
- INV-014 (User)
- INV-015 (Role)

Corresponding real sources (file_editor view these):
- redmine-master/app/models/project.rb
- redmine-master/app/models/issue.rb
- redmine-master/app/models/user.rb
- redmine-master/app/models/role.rb
- redmine-master/db/schema.rb (relevant portions)

Draft output path: .cc-rsg/drafts/05-data-model.md

Quality bar:
- Body ≥ 200 lines
- [REF: path:Lstart-Lend] ≥ 10
- fenced code blocks ≥ 3
- Mermaid diagrams ≥ 1 (ER diagram)
- ≥ 5 files under ## Sources Read

When done, return the chapter's key points + a list of detail questions raised.
The detail questions are material for the main agent to append into questions.json.

NOTE: If goal.output_language == "ja", render the chapter body, headings,
prose, and detail-question text in Japanese. Keep code blocks, file paths,
JSON keys, [REF: ...] markers, and the literal heading "## Sources Read"
in English.
\"\"\",
  subagent_type="chapter-investigator"
)
```

**Important constraints**:

- **Sequential execution (parallelism 1)**: OpenHands SDK's TaskManager runs them one at a time via an internal `threading.Lock`. 13 chapters → 13 sequential `task` calls. **Total time is NOT reduced**, but isolated per-chapter contexts improve quality.
- **Prompt cache is NOT shared**: each sub-agent has an isolated LLM context, so token usage is 5–10× the main agent. ChatGPT Plus subscription users hit caps quickly — **Anthropic API / OpenAI API modes are recommended**.
- **The sub-agent writes the chapter draft directly via `file_editor`** (saved as a file, NOT returned in the task result text). The main agent reads the return value and appends detail questions into `questions.json`.
- **Invoke once per chapter**. Bundling all chapters into one `task` call defeats the purpose (isolated contexts disappear).

**When the `task` tool is unavailable**, the main agent performs STEP A-F itself per chapter (pre-v2 behaviour).

---

### 🆕 outline-mode chapter writing (when `depth_mode == "outline" | "interactive"`)

This section does NOT apply in `comprehensive` mode. In outline mode, Phase 3's behaviour is replaced by OUT-A through OUT-D below.

#### OUT-A: Generate Layer 1 chapters (02-entities / 03-actions / 04-data / 05-dependencies)

Each Layer 1 chapter **exhaustively lists the "overview table" for that language**. Procedure:

1. Consult `.cc-rsg/skill/references/outline-tables.md` for the per-language catalogue.
2. **Use `glob` + `grep` to mechanically extract every entity**:
   - Ruby/Rails models: `grep "^class \\w+" --type ruby app/models/`
   - Controllers: `grep "^class \\w+Controller" --type ruby app/controllers/`
   - Etc., using the patterns from outline-tables.md for the target language.
3. Render the result as an **exhaustive Markdown table** — no omissions. 1 entity = 1 row.
4. Always add a **Confidence label** in each cell (🟢 VERIFIED / 🟡 INFERRED / 🔴 ASSUMED):
   - 🟢: the file of that entity was confirmed via `file_editor view`
   - 🟡: only the `grep` hit was confirmed; body unread
   - 🔴: inference based on framework-typical behaviour
5. The summary column is 1 line (≤ 80 characters). **Do not write detailed logic** — leave that to Layer 3 deep-dives.

**At the end of each chapter you MUST place a "deep-dive candidates" section** (see OUT-C).

#### OUT-B: Generate Layer 2 chapter (06-diagrams) — Mermaid

- ER diagram (auto-derived from Entities + Data tables)
- Module dependency diagram
- Representative sequence (1–3 of the most typical request flows)
- State-transition diagram (when key entities have `status` columns, etc.)

Each diagram has a **one-line caption** and a "how to read this" hint. If a diagram cell is `[INFERRED]`, say so explicitly.

#### OUT-C: "Deep-dive candidates" list at the end of each Layer 1 chapter

Place at the end of each chapter, using this format:

```markdown
### Deep-dive candidates (refer to them by ID)

- **D-001**: M-013 `Issue` class — authorisation guard logic [🔴 ASSUMED, complex]
- **D-002**: C-018 `ProjectsController#index` — visibility decision [🟡 INFERRED, business-critical]
- **D-003**: Sequence "Issue notification delivery" — subscribers resolution [🔴 ASSUMED]
```

Selection criteria (see the end of references/outline-tables.md):
1. Rows with many 🔴 ASSUMED labels.
2. High-complexity rows (top 10% by method count / association count / file line count).
3. Rows containing business-critical keywords (auth / payment / permission / audit, etc.).

#### OUT-D: Drop the body-length constraints

In outline mode:
- **The "200 lines / 10 REFs / 5 Sources Read" requirements do NOT apply.**
- Instead the MECE criterion is "**every entity appears in some row of some table**" (Phase 4's `coverage-check.py` decides this automatically).
- The chapter body consists of: table + 1–2 paragraphs of explanation + Mermaid diagrams (where applicable) + the deep-dive candidates list.

---

### Phase-specific cautions
- **In `comprehensive` mode**: writing a chapter without reading the code is forbidden. You may cite only files listed in Sources Read. ≥ 200 lines / ≥ 10 REFs / ≥ 5 Sources Read must be satisfied.
- **In `outline` / `interactive` mode**: "exhaustive entity listing" takes precedence. Apply Confidence labels honestly per cell — do NOT over-apply 🟢 (only for files actually viewed).
- Cross-chapter consistency is checked in Phase 4.
- Do not hide uncertainty markers; keep them explicit in the draft. They are the starting point for Phase 5 dialogue.

---

## Phase 4: Verify (checks + loopback)

### Purpose
Run inventory cross-check, per-chapter quality metrics, MECE check, and consistency checks automatically, looping failing chapters back to Phase 3.

### Procedure

1. **Generate trace.json**
   ```bash
   python .cc-rsg/skill/scripts/build-trace.py --cc-rsg-dir .cc-rsg --target-dir-for-required drafts
   ```
   This resolves every `[REF: path:line]` in `drafts/*.md` to a SRC unit and produces the MECE aggregation.

2. **Run coverage-check.py**
   ```bash
   python .cc-rsg/skill/scripts/coverage-check.py \
     --cc-rsg-dir .cc-rsg \
     --target-dir-for-required drafts \
     --output-format text
   ```
   Checks all of the following at once:
   - inventory count (min: `max(50, files / 20)`)
   - macro-type INV ratio (max 20%)
   - covered_by fill rate (90%)
   - per-chapter body lines (≥ 200), `[REF:]` count (≥ 10), code blocks (≥ 3), Mermaid (≥ 1), Sources Read items (≥ 5)
   - questions count (≥ 10), open ratio (≤ 20%)
   - MECE coverage (≥ 70%)

3. **Failure → loop back to Phase 3**
   - When `exit code` is 1, read the "gate decision" section of the output and:
     1. Identify the failed chapter (e.g. `chapter 05-data-model.md: [REF:] count is 7 < required 10`)
     2. **Read additional sources** corresponding to the chapter's `assigned_inventory_ids`
     3. Add to Sources Read, raise `[REF:]` count, thicken the body
     4. Re-run coverage-check.py
   - Maximum iterations: **3**. If a chapter still fails after 3 attempts, record it in `99-unresolved.md` as "insufficient quality" and continue.

4. **Cross-reference verification**
   - Check whether any cross-chapter inconsistency exists for the same concept.
   - File inconsistencies into `questions.json` with `priority: critical`.

5. **Deduplicate questions**
   - Detect duplicates across the entire Question Bank.
   - Merge only the "obviously identical"; flag the "similar but subtly different" as groups for Phase 5 confirmation.

6. **Save the verification report**
   - Save `coverage-check.py --output-format json` output to `.cc-rsg/coverage-report.json`.
   - Save a human-readable version to `.cc-rsg/coverage-report.md`.

7. **Phase 4 complete**
   - Once every chapter passes (or hits the 3-attempt qualitative limit), update `state.json` and proceed to Phase 5.

### Phase-specific cautions
- **Do not proceed to Phase 5 until coverage-check.py PASSes** (up to 3 loop iterations).
- The loopback is not "padding the prose" — its purpose is to **read more real code, add more citations, and thicken the explanation**.
- Missing cross-chapter inconsistencies makes Phase 5 dialogue explode. Squash them in Phase 4.

---

## Phase 5: Refine via Dialogue

### Purpose
Through dialogue with the user, resolve uncertainty markers and the Question Bank, refining the spec.

### 🚨 v2: all 3 stages are mandatory

`coverage-check.py` enforces `--max-open-ratio 0.2`, so leaving more than 20% of items as `open` blocks progression to Phase 6. Run all 3 stages.

#### Stage 1: Present the big picture (mandatory, once)

Ask the user **a single question** via `ask_user_question`:

```
Unresolved questions: N items
Per-category breakdown: business_rule X, architecture Y, data_model Z, ...
Per-severity breakdown: critical X, important Y, nice-to-have Z

Pick a progress mode:
- Answer every question one by one (most thorough)
- Answer only critical ones (faster)
- Mark every remaining question abandoned and skip to Phase 6 (fastest, lower quality)
```

choices: `["Answer all", "Critical only", "Skip with abandoned"]`, allow_free_text: true

#### Stage 2: Present critical clusters (mandatory, at least 3 clusters)

If Stage 1 selects "Answer all" or "Critical only", group the critical questions into related clusters.
**At least 3 clusters** are required (if fewer naturally, split mid-grain).

Present each cluster as one `ask_user_question`:
```
Business-rule cluster A (#Q-005, #Q-008, #Q-012)
These are questions around the purchase flow.
Answer them in sequence?

- Answer in sequence (recommended)
- Postpone this cluster
- Mark this cluster abandoned
```

#### Stage 3: Per-question dialogue (the rest of the questions)

Present each question via `ask_user_question`:

- **question**: the relevant code excerpt + tentative assumption + risk
- **choices**: `["Inference is fine (reflect in spec)", "Enter the correct answer", "Need SME confirmation, skip", "Cannot ever resolve (abandoned)"]`
- **allow_free_text**: true

Reflect the answer into the corresponding entry in `questions.json`:
- `Inference is fine` → `status: answered`, `answer: <tentative inference>`
- `Enter the correct answer` → `status: answered`, `answer: <user free-form input>`
- `Need SME confirmation` → `status: skipped`
- `abandoned` → `status: abandoned`

### To prevent Phase 5 "padding" by the agent

**If `questions.json` has fewer than 10 entries**:
- Before starting Phase 5, review the Phase 3 drafts and extract at least 5 ambiguous spots into `questions.json`.
- Extraction angles:
  - Spots where the naming convention or design intent is unclear
  - Spots where the business rule can only be inferred
  - Spots where error-handling policy admits multiple interpretations
  - Special implementations diverging from framework defaults
  - Handling of unused / deprecated code

### Applying answers

- Reflect each answer into the corresponding chapter draft (remove or update uncertainty markers).
- Fill in `[BLOCKED: see Q-NNN]` sections.

### Re-reconnaissance (only when needed)

If the answer makes additional investigation necessary, re-`file_editor view` the relevant code as an extra step in Phase 3 and update the chapter.

### Phase 5 completion criteria

Satisfy `coverage-check.py`'s `--max-open-ratio 0.2` criterion:
- At least 80% of all questions are `answered` / `skipped` / `abandoned`
- Strictly less than 20% remain `open`
- Continue Phase 5 until this is reached.

### Phase-specific cautions
- Skipping Stage 1 / Stage 2 and doing only Stage 3 is forbidden (the user loses the big picture).
- Demanding SME-grade answers for every question breaks the dialogue. `nice-to-have` items are allowed to remain as inferences.
- `abandoned` is reserved for "truly unanswerable in the long term" cases — do not abuse it as a shortcut.

---

## Phase 6: Deliver

### Purpose
Output the final spec as Markdown under `.cc-rsg/final/`.

### Procedure

File names follow the ASCII slug convention finalised in Phase 2 (`^(0\d|[1-9]\d)-[a-z0-9-]+\.md$`; reserved files: `00-metadata.md` / `99-unresolved.md` / `traceability.md`). Phase 6 does not create new names; it fills in the skeleton files generated in Phase 2.

1. **Merge chapter drafts**
   - Copy each chapter from `drafts/` to `.cc-rsg/final/` in the template-defined order.
   - Do NOT change the file names (use the ASCII slug names finalised in Phase 2).
   - Strip the meta comment at the top of each chapter file.

2. **Generate the traceability table (fill in `traceability.md`)**
   - Phase 2 created `traceability.md` as an empty file; write its body now.
   - Generate a table mapping each chapter/section to the source code it references.
   - Format example:

   ```markdown
   | Spec section | Source |
   |----------------|--------|
   | 3.2 User deactivation | src/jobs/UserDeactivationJob.php:12-58 |
   ```

3. **Generate the "Unresolved items" chapter (fill in `99-unresolved.md`)**
   - Phase 2 created the empty file; write its body now.
   - Aggregate `questions.json` entries with `status: abandoned`.
   - For each unresolved item, record "why it could not be resolved", "how far we inferred", "what is needed to resolve it in the future".
   - The chapter title in the body follows `goal.json.output_language` (EN example: `Chapter 99: Unresolved Items` / JA example: 「第99章: 未確定事項」). The file name `99-unresolved.md` is fixed regardless of language.

4. **Generate metadata (fill in `00-metadata.md`)**
   - Phase 2 created the empty file; write its body now.
   - Include: generation timestamp, commit hash of the target codebase (if available), goal definition finalised in Phase 0, template selection result, cc-rsg version.

5. **Final deliverable layout**
   ```
   .cc-rsg/final/
   ├── 00-metadata.md       # metadata (created Phase 2, filled Phase 6)
   ├── 01-overview.md       # Chapter 1: Overview
   ├── 02-architecture.md   # Chapter 2: Architecture
   ├── 03-...each chapter...md
   ├── 99-unresolved.md     # Unresolved items (created Phase 2, filled Phase 6)
   ├── traceability.md      # Traceability table (created Phase 2, filled Phase 6)
   └── README.md            # Reader's guide for the deliverable (generated in Phase 6)
   ```
   Note: file names are ASCII slug-fixed (language-independent). Chapter titles in the body follow `goal.json.output_language` (EN example: `# Chapter 1: Overview` / JA example: `# 第1章: 概要`).

6. **Completion notification**
   - Report to the user the deliverable location, the total page (or section) count, number of resolved questions, and number of unresolved items.
   - Mark `state.json` as complete.

### Phase-specific cautions
- The "unresolved items" chapter (`99-unresolved.md`) must NOT be omitted. It is the root of the spec's credibility.
- Omitting the metadata chapter (`00-metadata.md`) loses "when, from which version of the code" the spec was generated.
- Omitting the traceability table (`traceability.md`) makes every statement's origin untraceable.
- The presence of the three required files (`00-metadata.md` / `99-unresolved.md` / `traceability.md`) is verified by `scripts/coverage-check.py`; missing files raise errors.

---

## 🆕 Phase 6.5: Deep-dive acceptance mode (when `depth_mode` is `outline` or `interactive`)

### Purpose

In `outline` / `interactive` modes, the spec at the end of Phase 6 is only "overview tables + Mermaid + deep-dive candidates". **The user reading the spec points out items of interest and asks for on-the-spot deep-dives** — that is the essence of these modes. Phase 6.5 holds the agent in a **deep-dive acceptance state**, waiting for explicit user instructions, until the env is closed.

### Behaviour

After the Phase 6 completion report, the agent emits the following message and **waits for input**:

```
✅ Overview spec generation is complete (X chapters / Y tables / Z deep-dive candidates).

Check the "Deep-dive candidates" section at the end of each chapter.
For items of interest, instruct like this:

- By candidate ID:  "Deep-dive D-001" / "D-007"
- By entity ID:    "Tell me more about M-013 Issue" / "C-018 ProjectsController"
- By natural text: "Explain the authorisation model" / "How does Issue notification delivery work?"

To end the deep-dive mode, reply "end" / "complete" / "OK, done".
```

### Recognising and processing instructions

Recognise user input via the following patterns:

1. **Explicit ID (highest priority)**: matches `D-NNN` / `M-NNN` / `C-NNN` / `T-NNN`, etc. → look up the row/candidate in `wbs.json` / `inventory.json` / per-chapter tables → obtain the file and overview.
2. **Direct entity name**: `Issue class` / `ProjectsController`, etc. → identify the file via `grep`.
3. **Natural-language topic**: keywords like `authorisation` / `notification` / `payment` → keyword-search the relevant chapters/table rows, present the top 3 to the user, and ask "Which one do you want to deep-dive?".

### Generating a deep-dive chapter

Once the deep-dive target is fixed:

1. Launch the `chapter-investigator` sub-agent via the `task` tool.
2. Sub-agent prompt:
   - Target entity / candidate ID and overview
   - List of related real source files
   - "Write 1 chapter at **comprehensive-mode-equivalent quality**" (≥ 200 lines, ≥ 10 REFs, ≥ 1 Mermaid, ≥ 5 Sources Read)
   - Output path: `.cc-rsg/drafts/deep/D-NNN-{slug}.md` or `M-NNN-{slug}.md`
3. Display the key findings returned by the sub-agent in the main thread.
4. **Update traceability.md** (append the deep-dive chapter).
5. **Update the relevant row in the original Layer 1 chapter**: bump the confidence from 🟡/🔴 → 🟢, add a "see deep-dive `D-001`" link.
6. Report completion and return to the input-waiting state.

### Ending

When the user sends a completion word ("end", "complete", "OK, done", etc.):

1. Update `state.json` with `phase_6_5_completed_at`.
2. Re-generate `final/` (consolidating the deep-dive chapters).
3. Update final/traceability.md to the final version.
4. Close the env with a thank-you message.

### Phase-specific cautions

- **While waiting for user input, the agent does NOT poll or self-progress**. It moves only after an explicit instruction.
- If a deep-dive is **requested for a target already covered**, surface the existing deep-dive chapter and ask "Regenerate it?".
- Sub-agent return values during deep-dive also follow the **mode B contract** (path + summary), not the full body.
- Be mindful of cumulative cost: each deep-dive equals roughly one comprehensive chapter. Periodically report "N deep-dives so far, cumulative cost ~$X".

---

## Question Bank operation

### Data structure

Each entry in `.cc-rsg/questions.json` has the following fields:

```json
{
  "id": "Q-042",
  "generated_at_phase": "investigation",
  "category": "business_rule",
  "body": "Is the 3-retry of this payment process driven by a technical constraint or a business requirement?",
  "evidence": {
    "file": "src/payment/PaymentRetryHandler.php",
    "lines": "45-58",
    "code_excerpt": "for ($i = 0; $i < 3; $i++) { ... }"
  },
  "related_inventory_ids": ["INV-027"],
  "severity": "important",
  "resolution_type": "ask_sme",
  "status": "open",
  "answer": null,
  "answerer": null,
  "answered_at": null,
  "related_question_ids": []
}
```

### 7 standard categories

1. **business_rule**: business rules
2. **architecture_decision**: architecture decisions
3. **data_model_intent**: data-model intent
4. **external_integration**: external-system integration
5. **naming_history**: naming and historical context
6. **operational_requirement**: operational requirements
7. **security_compliance**: security / compliance

Users may add custom categories as needed (v1 expects manual JSON editing; UI is a future extension).

### Severity levels

- **critical**: cannot write the chapter without resolving this. The sub-agent leaves the section blank (`[BLOCKED]`).
- **important**: can be written with inference but confidence is low. Leave a `[CONFIDENCE: LOW]` marker.
- **nice-to-have**: a question about fine detail. Write with inference and lightly confirm in Phase 5.

### Status transitions

```
open → asked → answered
            ↓
            abandoned
```

---

## Sub-agent behaviour

### Sub-agent prompt template (skeleton)

The prompt skeleton handed to the Task tool in Phase 3. The complete version lives in `references/subagent-prompt.md`.

```
You are an investigation agent in charge of a specific chapter.

[Goal definition (excerpt from goal.json)]
- Output language: {output_language}  ("en" or "ja")
- Primary reader: {primary_reader}
- Granularity: {granularity}
- Perspectives: {perspectives}

[Output-language handling]
- The chapter body, headings, prose explanations, annotations on uncertainty markers, and the chapter-end detail-question list are ALL rendered in {output_language}.
- Machine-readable elements — file names (ASCII slug), `[REF: file:lines]`, `[CONFIDENCE: HIGH|MED|LOW]`, `[ASK SME]`, `[ASSUMED: ...]`, `[BLOCKED: see Q-XXX]`, IDs (`Q-XXX` / `INV-XXX`) — stay English regardless of {output_language}.
- Even when the reference assets (`templates/*.md`, `references/*.md`) are written in Japanese, when {output_language} == "en" you must dynamically translate the chapter heading examples and body samples into semantically equivalent English before writing the chapter body.

[Assigned chapter]
- Chapter title: {chapter_title}
- Inventory items to cover: {inventory_ids}
- Template definition (the structure of this chapter): {template_section}

[Working instructions]
1. Carefully read the source code corresponding to the assigned inventory items.
2. Write the chapter body.
3. For every statement, attach a `[REF: file:lines]` citation with precise line ranges.
4. Do not hide uncertainty; use the following markers:
   - [CONFIDENCE: HIGH | MED | LOW]
   - [ASK SME]
   - [ASSUMED: <inference>; basis: <evidence>]
   - [BLOCKED: section left empty because of a critical question]
5. At the end of the chapter, append a "detail questions raised in this chapter" list.

[Constraints]
- Never conflate inference with fact.
- Do not write detail beyond the goal granularity.
- When a critical question is hit, leave the section as [BLOCKED] and report completion.

[Output format]
{See references/subagent-prompt.md for details}
```

### Sub-agent decision logic

When a question is encountered, the sub-agent follows this pseudocode:

```
if question.severity == "critical":
    leave the section as [BLOCKED: see Q-XXX]
    register the question in the Question Bank
    finish the rest of the chapter as much as possible
    report completion
else:
    leave a [CONFIDENCE: LOW; ASSUMED: <inference>] marker
    inferred best-effort completion of the chapter
    register the question in the Question Bank
    report completion
```

---

## State management and resume

### Schema of `state.json`

```json
{
  "current_phase": 3,
  "phase_progress": {
    "phase_3": {
      "total_subtasks": 12,
      "completed_subtasks": 8,
      "blocked_subtasks": ["chapter_payment", "chapter_auth"]
    }
  },
  "started_at": "2026-05-01T10:00:00+09:00",
  "last_updated": "2026-05-01T14:32:15+09:00",
  "session_history": [
    {"timestamp": "2026-05-01T10:00:00+09:00", "phase": 0, "event": "started"},
    {"timestamp": "2026-05-01T10:15:00+09:00", "phase": 1, "event": "transitioned"}
  ]
}
```

### Resume behaviour

When the skill detects an existing `.cc-rsg/state.json` at startup, present the situation in the resume message and confirm the user's intent. If `.cc-rsg/goal.json` is readable, the resume message is rendered in its `output_language`. Only when `goal.json` itself is missing (so the language is unknown) the bilingual format (English first, then Japanese) is used — identical in shape to Phase 0 Step 3 — to prompt the language selection again.

**Resume-message template (English version, when `output_language: "en"`)**:

```
A previous cc-rsg session is in progress. The current state is:

- Current phase: Phase 3 (Investigate)
- Progress: 8 of 12 sub-tasks completed; 2 BLOCKED on critical questions
- Question Bank: 23 unresolved questions (2 critical)
- Last updated: 2026-05-01 14:32

What would you like to do?
(A) Resume from where it stopped (finish remaining Phase 3 tasks)
(B) Roll a phase back (resume from a specified phase)
(C) Full reset (delete .cc-rsg/ and start from Phase 0)
(D) Show detailed state, then decide
```

**Resume-message template (Japanese version, when `output_language: "ja"`)**:

```
前回のセッションで cc-rsg を実行しています。状況は以下の通りです。

- 現在のフェーズ: Phase 3 (Investigate)
- 進捗: 12サブタスク中8件完了、2件は critical な疑問により BLOCKED 状態
- Question Bank: 未解決疑問 23件(うち critical: 2件)
- 最終更新: 2026-05-01 14:32

以下のいずれを実施しますか?
(A) 続きから再開(Phase 3 残タスクを完了させる)
(B) Phase を巻き戻す(指定する Phase から再開)
(C) 全リセット(.cc-rsg/ を削除して Phase 0 から開始)
(D) 状況を詳細表示してから判断する
```

Per-phase resume message details will be moved into a separate doc in a follow-up.

---

## Reference docs and templates

The skill depends on the following reference docs and templates. They live under `references/` and `templates/` next to this file.

### Under `references/`

- `references/inventory-units.md`: per-language / per-framework inventory unit definitions (PHP, COBOL, Python, Java, JavaScript/TypeScript, C#, etc.)
- `references/template-catalog.md`: template selection guide
- `references/question-categories.md`: 7-standard-category details and how to add custom categories to the Question Bank
- `references/verification-checklists.md`: verification checklists used in Phase 4
- `references/subagent-prompt.md`: the complete sub-agent prompt used in Phase 3
- `references/outline-tables.md`: per-language overview-table catalogue for outline mode

### Under `templates/`

- `templates/web-app.md`: web-application spec template
- `templates/batch-system.md`: batch-system spec template
- `templates/api-service.md`: API-service spec template
- `templates/library-sdk.md`: library / SDK spec template

### Under `scripts/`

- `scripts/source-map.py`: scans the target codebase for source units and produces `source-map.json`
- `scripts/build-trace.py`: resolves `[REF:]` markers in drafts against source-map.json into `trace.json`
- `scripts/build-traceability.py`: renders human-readable `traceability.md` from `trace.json`
- `scripts/coverage-check.py`: verifies inventory coverage, draft quality, MECE, etc. (Phase 4)

---

## File layout

### The skill bundle (when distributed)

```
.claude/skills/cc-rsg/
├── SKILL.md                          (this file)
├── agents/
│   └── chapter-investigator.md
├── references/
│   ├── inventory-units.md
│   ├── template-catalog.md
│   ├── question-categories.md
│   ├── verification-checklists.md
│   ├── subagent-prompt.md
│   └── outline-tables.md
├── templates/
│   ├── web-app.md
│   ├── batch-system.md
│   ├── api-service.md
│   └── library-sdk.md
└── scripts/
    ├── source-map.py
    ├── build-trace.py
    ├── build-traceability.py
    └── coverage-check.py
```

### Working directory on the consumer project

```
.cc-rsg/
├── state.json          (current phase and progress)
├── goal.json           (Phase 0 answers)
├── recon-report.md     (Phase 1 reconnaissance output)
├── inventory.json      (all inventory items)
├── wbs.json            (Phase 2 work decomposition)
├── questions.json      (Question Bank)
├── drafts/             (per-chapter draft Markdown; file names follow the ASCII slug convention)
│   ├── 00-metadata.md      # created empty in Phase 2, filled in Phase 6
│   ├── 01-overview.md
│   ├── 02-architecture.md
│   ├── ...
│   ├── 99-unresolved.md    # created empty in Phase 2, filled in Phase 6
│   └── traceability.md     # created empty in Phase 2, filled in Phase 6
└── final/              (final deliverable; same file names as drafts)
    ├── 00-metadata.md
    ├── 01-overview.md
    ├── ...
    ├── 99-unresolved.md
    ├── traceability.md
    └── README.md
```

---

## Key implementation principles

### Honesty above polish
A polished, finished-looking spec is less valuable than an honest spec whose gaps are visible. Clearly separate what Claude inferred from what the code unambiguously says, and surface `abandoned` questions as "unresolved items".

### Guarantee traceability
Every statement must be traceable to a specific source-code location with a line range. This inherits the KDM (Knowledge Discovery Metamodel) "Source package" idea and is a hard requirement for a spec that maintenance developers can audit later.

### Respect progressive refinement
Do not aim for a perfect spec on the first pass. Phase 1 → overall picture; Phase 2 → skeleton; Phase 3 → chapter drafts; Phase 5 → refinement. Insert a user review at each phase.

### Guarantee resumability
For long-running analysis sessions, record progress / established facts / unresolved questions on the file system so the work can be paused and resumed at any time (inheriting the `.reversa/state.json` idea).

---

## Known issues and mitigations

### Phase 1 reconnaissance does not finish because the codebase is too large
- Explicitly narrow the scope (a specific module inside a monorepo, etc.).
- Consider adding a "target scope" question to the 5 goal-definition questions in Phase 0.

### Sub-agent context explodes during parallel investigation
- Keep "1 sub-agent = 1 chapter" as the principle; subdivide chapters further to keep individual contexts small.
- Pass only the relevant excerpts of `goal.json` and `inventory.json`; do not pass unrelated files.

### The Question Bank grows unmanageable, breaking the dialogue
- Use Phase 4 normalisation to merge duplicates.
- Filter by severity; talk through `critical` items first.

### The user cannot spare time for the reviews
- Design the per-phase reviews as "approve to move on".
- Allow postponing detailed review until the final deliverable in Phase 6, and reviewing the whole thing in one batch.

---

## Versioning and changelog

- v0.1.0 (2026-05-01): initial draft. Defines the Phase 0-6 state machine, Question Bank, sub-agent behaviour, and file layout.
- v0.4.0 (2026-06-09): English-base Phase 1. SKILL.md, agents/chapter-investigator.md, and variants/B/*.md translated to English with Phase 0 Step 3 defaulting to English; corresponding cc-rsg-web `skill.ts` regex switched to `### Phase-specific cautions`.

---

## License and distribution

MIT License. Designed to be released as open source.

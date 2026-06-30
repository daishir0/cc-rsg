# cc-rsg — Claude Code Reverse Spec Generator

> A Claude Code skill that reverse-engineers specification documents from existing codebases

📖 **日本語版は下記にあります** — [Jump to Japanese →](#日本語版)

`cc-rsg` is a general-purpose framework for automatically generating specification documents — for maintenance engineers or end customers — from legacy or active codebases.

It is the **reverse direction** counterpart of `cc-sdd` (Spec Driven Development): while `cc-sdd` goes "spec → code", `cc-rsg` goes "code → spec".

---

## Why This Was Built

Legacy system modernization, codebase onboarding for new engineers, deliverable spec docs, internal knowledge consolidation — across all these scenarios, the problem of "we have the code but no reliable specification" is universal.

In the LLM era, asking an AI to "make a spec from this code" produces visually polished documents instantly. But in practice, if that document turns out to be "beautiful fiction filled with guesses", it breaks down in production.

`cc-rsg` prioritizes:

- **Honesty**: Don't hide guesses — mark them explicitly. Show "unresolved items" as a dedicated chapter
- **Traceability**: Every statement has a source code reference with line numbers
- **Completeness**: Enumerate all extractable units from the code, mechanically verify coverage
- **Progressive elaboration**: Recon → skeleton → chapter drafts → verify → dialog refine
- **Resumability**: Long sessions can be paused and resumed

---

## Design Heritage

`cc-rsg` is positioned as the latest generation in the following lineage:

- **KDM (Knowledge Discovery Metamodel, ISO/IEC 19506:2012)**: Language-neutral structured knowledge representation
- **OMG ADM (Architecture-Driven Modernization)**: MDRE (Model-Driven Reverse Engineering)
- **Siala & Lano (2025)**: LLM × MDRE empirical integration research
- **Reversa** (OSS): Modern form of "agent-readable executable specifications"
- **IBM watsonx Code Assistant for Z / AWS Transform / CAST Imaging**: "Deterministic graph + LLM natural language" hybrid architecture

`cc-rsg` builds on these by maximizing Claude Code features (SKILL.md, subagents, AskUserQuestion, Task) into a general-purpose framework.

---

## Installation

### Place into your Claude Code environment

```bash
# As a project-level skill
mkdir -p .claude/skills/
cp -r skills/cc-rsg .claude/skills/

# Or as a user-level skill
mkdir -p ~/.claude/skills/
cp -r skills/cc-rsg ~/.claude/skills/
```

### Verify installation

Launch Claude Code and run `/help` — `cc-rsg` should appear in the skill list.

---

## Usage

### Basic Flow

```
1. Launch Claude Code at the target codebase root
2. Invoke the cc-rsg skill
3. Answer the 5-question goal definition (Phase 0)
4. Review recon results and pick a template (Phase 1)
5. Review the WBS and inventory (Phase 2)
6. Wait for parallel subagent investigation (Phase 3)
7. Review the verification report (Phase 4)
8. Refine the spec via Question Bank dialogue (Phase 5)
9. Receive the final deliverables (Phase 6)
```

### Pause and Resume

Even if you interrupt the session, progress is saved to `.cc-rsg/state.json`. On the next Claude Code launch, a resume message appears with options: continue / rewind / full reset.

### Output Location

A `.cc-rsg/` directory is created at the root of the target project, containing:

```
.cc-rsg/
├── state.json          # Progress tracking
├── goal.json           # Phase 0 goal definition
├── recon-report.md     # Phase 1 reconnaissance
├── inventory.json      # All inventory items
├── wbs.json            # Work breakdown
├── questions.json      # Question Bank
├── drafts/             # Per-chapter drafts
└── final/              # Final deliverables
```

---

## Language

Starting **v0.4.0**, the entire skill bundle (`SKILL.md`, `agents/`, `templates/`, `references/`, and the docstrings/messages of `scripts/`) is **English-base**. The default for `goal.json.output_language` is `"en"`.

Japanese output is fully supported: select `日本語 (Japanese)` in Phase 0 Step 3, and the agent dynamically renders chapter bodies, AskUserQuestion bodies, and progress messages in Japanese while preserving every machine-readable element (`## Sources Read`, `[REF: ...]`, `[CONFIDENCE: ...]`, JSON keys, file slugs, ID prefixes) verbatim in English. See SKILL.md Principle #11 for the full contract.

---

## 6+1 Phase State Machine

| Phase | Name | Main Action |
|-------|------|-------------|
| 0 | Setup & Goal | 5-question goal definition (scope, reader, granularity), output language |
| 1 | Recon & Template | Shallow reconnaissance, template selection, **depth mode decision** |
| 2 | Plan & WBS | Skeleton generation, inventory extraction, WBS (branches on depth mode) |
| 3 | Investigate | Per-chapter independent sub-agent investigation (comprehensive: STEP A–G / outline: OUT-A–D) |
| 4 | Verify | Coverage, integrity, 11-item validation with loopback fixes |
| 5 | Refine via Dialogue | 3-stage (overview / critical clusters / individual) dialog to resolve uncertainty |
| 6 | Deliver | Output final deliverables to `.cc-rsg/final/` |
| **6.5** | **Interactive Deep-Dive** | (interactive mode only) On-demand deep-dive chapter generation guided by user |

See [`skills/cc-rsg/SKILL.md`](skills/cc-rsg/SKILL.md) for details.

---

## Depth Modes

Three depth modes are selectable at the end of Phase 1, based on codebase scale and reader purpose.

| Mode | Use Case | Chapter Body Format |
|------|----------|---------------------|
| **`comprehensive`** | Audit / regulatory compliance — full coverage required | Each chapter: 200+ lines, 10+ `[REF:]` markers, 1+ Mermaid diagram |
| **`outline`** (recommended default) | General use, large codebases | Enumerated tables of Modules / Entities / Actions / Data / Dependencies + Mermaid + deep-dive candidate lists |
| **`interactive`** | Team reference, iterative refinement | Same as outline + Phase 6.5 accepts user-directed deep-dives |

For codebases of 200 files or fewer, `comprehensive` is auto-selected. Above that threshold, the user is prompted to choose.

In `outline` / `interactive` modes, each table cell is mandatorily tagged with a **Confidence label** (🟢 VERIFIED / 🟡 INFERRED / 🔴 ASSUMED) to clearly distinguish guesses from confirmed facts. Deep-dive candidates are auto-selected based on 🔴 ASSUMED density, top-decile complexity, and business-critical keyword matches (auth / payment / permission / etc.).

---

## Supported Languages and Typical Units

`references/inventory-units.md` covers the following languages:

- PHP (Laravel / Symfony / CakePHP, etc.)
- COBOL (+ JCL)
- Python (Django / Flask / FastAPI, etc.)
- Java / Kotlin (Spring Boot, etc.)
- JavaScript / TypeScript (Express / Next.js / NestJS / Expo / React Native / React, etc.)
- C# (ASP.NET Core, etc.)
- Go
- **Ruby on Rails**: 14-unit catalog covering Controller / Model / Concern / Service / Job / Mailer / Helper / Lib / Migration / Route / View / JS module / config / Mailer template

Overview-table definitions for `outline` mode are in `references/outline-tables.md`, providing ripgrep-based exhaustive-enumeration patterns for 6 stacks: Ruby/Rails, Python/Django, JS/TS/React, Go, Java/Kotlin (Spring Boot).

Dedicated extraction guides are provided for major frameworks:

- **Flask**: Blueprints, view functions, hooks, Jinja2 templates, Flask-WTF forms, Flask-SQLAlchemy models, CLI commands
- **FastAPI**: APIRouter, Pydantic schemas, Dependencies, Background tasks, Middleware, Exception handlers, Security schemes
- **Next.js** (App Router / Pages Router): page / route / layout / Server Action / Middleware, with mixed-router support
- **Expo / React Native**: Screens, Navigators, native modules, `app.json` / `eas.json`, permissions, Managed / Bare Workflow detection

Inventory **granularity rules** are also built in: minimum count (`max(50, file_count // 20)`) and macro-unit ratio caps are mechanically enforced by the Phase 4 verification script.

### Mechanical source map v2 (role-typed)

`scripts/source_map_v2/` is a framework-aware, **tree-sitter-based** extractor (schema 0.2.0) that maps every unit onto the five universal tables (Modules / Entities / Actions / Data / Dependencies) and role-types it — `endpoint` (with HTTP method + path), `model`, `schema`, `component`, `job`, `route_group`, `migration`, `datastore`, … — across **9 languages**: Python, TypeScript/JavaScript, Ruby/Rails, PHP, Java, C#, Go, SQL, COBOL. Framework detection (FastAPI / Django / Flask / Rails / Laravel / Spring / Next.js / Express / NestJS, …) selects the right unit kinds. It coexists with the v1 `source-map.py` and is backward compatible. tree-sitter is an **optional** dependency; languages without a grammar fall back to file-level units with a loud warning (never a silent drop). Run it standalone:

```bash
python -m source_map_v2 --target <root> --output .cc-rsg/source-map.json
```

Unsupported languages or frameworks can be added on request via GitHub Issues.

---

## Templates

Initial set of 4 templates included:

- **Web Application Spec** (`templates/web-app.md`)
- **Batch System Spec** (`templates/batch-system.md`)
- **API Service Spec** (`templates/api-service.md`)
- **Library/SDK Spec** (`templates/library-sdk.md`)

Users can also bring their own templates.

---

## Question Bank

`cc-rsg` accumulates questions raised during investigation in `.cc-rsg/questions.json`.

### 7 Standard Categories

1. **business_rule**
2. **architecture_decision**
3. **data_model_intent**
4. **external_integration**
5. **naming_history**
6. **operational_requirement**
7. **security_compliance**

### Severity

- **critical**: Chapter cannot be written without resolving this
- **important**: Can be written by guess but with low confidence
- **nice-to-have**: Detail-level refinement

### Unanswerable Questions

Questions that will never get an answer ("the SME left the company", "no one remembers the historical context") are marked as `abandoned` and explicitly recorded in the "Unresolved Items" chapter of the final spec.

This is the foundation of the spec's trustworthiness.

---

## Directory Structure

```
cc-rsg/
├── README.md
├── LICENSE
├── .gitignore
└── skills/
    └── cc-rsg/
        ├── SKILL.md
        ├── agents/
        │   └── chapter-investigator.md  # Per-chapter sub-agent definition
        ├── references/
        │   ├── inventory-units.md       # Language units + granularity rules + Rails catalog
        │   ├── outline-tables.md        # Overview-table definitions for outline mode (6 stacks)
        │   ├── template-catalog.md
        │   ├── question-categories.md
        │   ├── verification-checklists.md
        │   └── subagent-prompt.md
        ├── templates/
        │   ├── web-app.md
        │   ├── batch-system.md
        │   ├── api-service.md
        │   └── library-sdk.md
        ├── variants/
        │   └── B/                       # Optional Context Optimization mode B
        │       ├── README.md            # When and how to activate mode B
        │       ├── SKILL.phase3-stepG.md  # Phase 3 STEP G override
        │       └── chapter-investigator.md  # Mode-B sub-agent (return-value contract)
        └── scripts/
            ├── source-map.py            # Phase 2: source unit auto-extraction (v1)
            ├── source_map_v2/           # v2: role-typed, framework-aware, tree-sitter extractor (9 languages)
            │   ├── taxonomy.py          #   role vocabulary (5 universal tables)
            │   ├── model.py             #   source-map.json schema 0.2.0
            │   ├── detect.py            #   framework detection (layer 1)
            │   ├── pipeline.py          #   3-layer orchestrator
            │   ├── extractors/          #   per-language extractors (layer 2)
            │   └── tests/               #   acceptance tests
            ├── build-trace.py           # End of Phase 3 / Phase 4: build trace.json from [REF:] markers
            ├── build-traceability.py    # Phase 6: generate traceability.md
            └── coverage-check.py        # Phase 4: multi-item verification (comprehensive / outline modes)
```

---

## Status

Currently **v0.7.0** (source-map v2: a role-typed, framework-aware, tree-sitter-based mechanical extractor spanning 9 languages).

### Known Limitations

- Custom category addition requires manual JSON editing (UI mechanism is a future extension)
- MCP integration is not implemented (designed for standalone Claude Code)
- Slash command options (`--restart`, etc.) are not implemented

### Roadmap (tentative)

- ~~v0.2: Enforce chapter file naming and required files; naming/required-file checks in the verification script~~ (done)
- ~~v0.2: Per-chapter sub-agent delegation, Phase 4 loopback verification, granularity rules, Rails catalog, output-language selection~~ (done)
- ~~v0.3: Depth modes (comprehensive / outline / interactive), Phase 6.5 interactive deep-dive, outline-tables.md~~ (done)
- ~~v0.4: English-base migration of the entire skill bundle; bilingual output via `output_language`; README flipped to English-first~~ (done)
- ~~v0.5: Mermaid styling contract (host-themed palette), `user_custom_deliverables` enforcement, strict `[REF: path:line]` format, Phase 5 skip prevention, intent-vs-delivery audit, optional Context Optimization mode B variant~~ (done)
- ~~v0.6: Phase 0 bundle staging into `.cc-rsg/skill/`, `[REF:]` placeholder consistency (no leading `L`), Sources Read counter fix, Ruby top-level method extraction~~ (done)
- ~~v0.7: `scripts/source_map_v2/` — role-typed, framework-aware, tree-sitter-based mechanical source map (schema 0.2.0). Per-language extractors for Python, TS/JS, Ruby/Rails, PHP, Java, C#, Go, SQL, COBOL; framework detection; loud warnings instead of silent drops; coexists with v1 `source-map.py`~~ (done)
- v0.8: UI for custom categories, templates added based on user feedback; Kotlin extractor; wire source-map v2 role typing into Phase 2 inventory
- v1.0: Stable release after several real-project applications

---

## Preprint / Citation

The design rationale, intellectual lineage, and implementation decisions of this skill are detailed in the following preprint. Please cite when referring to this work in publications or talks.

> **Preprint**: https://zenodo.org/records/20541685

---

## License

MIT License. See [LICENSE](LICENSE).

---

## Contributing

Feedback, template requests, and bug reports are welcome via GitHub Issues.

Particularly welcome contributions:

- Inventory unit definitions for new languages/frameworks
- New templates (DWH, ML pipeline, IaC, mobile, etc.)
- Verification checklist additions
- Real-project application reports

---

## Related Projects

- **cc-sdd**: Spec Driven Development. The counterpart concept of `cc-rsg`
- **Reversa**: Similar OSS with a 5-phase pipeline

---

## Acknowledgments

The design draws significant inspiration from:

- The OMG community that standardized KDM (ISO/IEC 19506:2012)
- sandeco, the author of Reversa
- Siala & Lano (2025) "LLM4Models" paper
- Thoughtworks' review articles on AI-generated specifications

---

> "An honest spec with visible holes is more practically valuable than a polished spec full of fiction."
> — from the `cc-rsg` design principles

---
---

# 日本語版

# cc-rsg — Claude Code Reverse Spec Generator

> 既存のコードベースから仕様書を逆生成(リバースエンジニアリング)するための Claude Code スキル

📖 **English version is at the top** — [Jump to English →](#cc-rsg--claude-code-reverse-spec-generator)

`cc-rsg` は、レガシーまたは現役のコードベースから、メンテナンス担当者あるいは納品先顧客に向けた仕様書を自動生成するための汎用フレームワークです。

「コード → 仕様」の **reverse 方向** を担うスキルであり、`cc-sdd`(Spec Driven Development、仕様駆動開発)の対概念として位置づけられています。

---

## なぜ作ったのか

レガシーシステムのモダナイゼーション、新規参画エンジニアによるコードベース理解、納品物としての仕様書整備、社内ナレッジ整備 — これらの場面で「コードはあるが仕様書がない / 信頼できない」という課題は普遍的です。

LLM時代になり、AIに「このコードから仕様書を作って」と頼むだけで一見綺麗な仕様書が生成されるようになりました。しかし実務では、その仕様書が「推測で埋められた美しいフィクション」だった場合、本番で破綻します。

`cc-rsg` は以下を最優先します。

- **正直さ**: 推測した部分は隠さず明示する。「未確定事項」を独立した章として示す
- **トレーサビリティ**: すべての記述にソースコードの行番号付き参照を付ける
- **抜け漏れ防止**: コードから抽出可能な単位を全件列挙し、機械的にカバレッジを検証する
- **段階的詳細化**: 偵察 → スケルトン → 章ドラフト → 検証 → 対話精緻化、と段階を踏む
- **再開可能性**: 長時間のセッションを中断・再開できる

---

## 設計の系譜

`cc-rsg` の設計は以下の系譜の最新世代として位置づけられます。

- **KDM(Knowledge Discovery Metamodel、ISO/IEC 19506:2012)**: 言語非依存の中立的な構造化知識表現
- **OMG ADM(Architecture-Driven Modernization)**: MDRE(Model-Driven Reverse Engineering)
- **Siala & Lano (2025)**: LLM × MDRE の統合実証研究
- **Reversa**(OSS): エージェント可読な実行可能仕様という現代的形態
- **IBM watsonx Code Assistant for Z / AWS Transform / CAST Imaging**: 「決定論的グラフ + LLM自然言語化」のハイブリッドアーキテクチャ

`cc-rsg` はこれらを踏まえ、Claude Code の機能(SKILL.md、subagents、AskUserQuestion、Task)を最大限活用したフレームワークとして設計されています。

---

## インストール

### Claude Code 環境に配置

```bash
# プロジェクトのスキルとして配置する場合
mkdir -p .claude/skills/
cp -r skills/cc-rsg .claude/skills/

# または、ユーザーレベルのスキルとして配置する場合
mkdir -p ~/.claude/skills/
cp -r skills/cc-rsg ~/.claude/skills/
```

### 動作確認

Claude Code を起動し、`/help` でスキル一覧に `cc-rsg` が表示されれば成功。

---

## 使い方

### 基本フロー

```
1. 対象コードベースのルートで Claude Code を起動
2. cc-rsg スキルを呼び出す
3. ゴール定義5問に回答(Phase 0)
4. 偵察結果を確認しテンプレート選定(Phase 1)
5. WBS と インベントリをレビュー(Phase 2)
6. サブエージェントによる並列調査を待つ(Phase 3)
7. 検証レポートを確認(Phase 4)
8. Question Bank の対話で仕様を精緻化(Phase 5)
9. 最終成果物を受け取る(Phase 6)
```

### 中断と再開

セッションを中断しても、`.cc-rsg/state.json` に進捗が保存されます。次回 Claude Code 起動時に再開メッセージが表示され、続きから / 巻き戻し / 全リセット のいずれかを選択できます。

### 出力場所

利用プロジェクトの直下に `.cc-rsg/` ディレクトリが作成され、以下が保存されます。

```
.cc-rsg/
├── state.json          # 進捗管理
├── goal.json           # Phase 0 のゴール定義
├── recon-report.md     # Phase 1 の偵察結果
├── inventory.json      # 全インベントリ項目
├── wbs.json            # 作業分解
├── questions.json      # Question Bank
├── drafts/             # 各章のドラフト
└── final/              # 最終成果物
```

---

## 言語 (Language)

**v0.4.0** から、スキル本体一式 (`SKILL.md` / `agents/` / `templates/` / `references/` / `scripts/` の docstring・メッセージ) は **英語ベース** になりました。`goal.json.output_language` のデフォルトは `"en"` です。

日本語出力は引き続き完全サポート: Phase 0 Step 3 で `日本語 (Japanese)` を選択すると、章本文・AskUserQuestion 質問文・進捗メッセージ等の自然言語出力が日本語で動的に生成されます。ただし機械可読要素 (`## Sources Read`、`[REF: ...]`、`[CONFIDENCE: ...]`、JSON キー、ファイル名 slug、ID prefix 等) は言語に関わらず英語固定です。詳細は SKILL.md の Principle #11 を参照。

---

## 6+1フェーズ状態マシン

| Phase | 名称 | 主な動作 |
|-------|------|---------|
| 0 | Setup & Goal | ゴール定義5問で対象範囲・読者・粒度を確定、出力言語選択 |
| 1 | Recon & Template | 浅い偵察を行い、仕様書テンプレートを選定、**depth モード判定** |
| 2 | Plan & WBS | スケルトン生成、インベントリ抽出、WBS分割(depth モードで章構成分岐) |
| 3 | Investigate | サブエージェントで各章を独立調査(comprehensive: STEP A〜G / outline: OUT-A〜D) |
| 4 | Verify | カバレッジ・整合性・11項目検証・ループバック修正 |
| 5 | Refine via Dialogue | 3段階(全体像/criticalクラスタ/個別)対話で不確実性を解消 |
| 6 | Deliver | 最終成果物を `.cc-rsg/final/` に出力 |
| **6.5** | **Interactive Deep-Dive** | (interactive モード時のみ) 利用者の指示で深掘り章を on-demand 生成 |

詳細は [`skills/cc-rsg/SKILL.md`](skills/cc-rsg/SKILL.md) を参照してください。

---

## Depth モード

対象コードベースの規模・読者用途に応じて、Phase 1 末尾で以下3つの深度モードから選択します。

| モード | 用途 | 章本文の形 |
|-------|------|----------|
| **`comprehensive`** | 監査・規制対応など完全網羅が必要な場合 | 各章 200 行以上、`[REF:]` 10件以上、Mermaid 1個以上 |
| **`outline`** (推奨デフォルト) | 通常用途、大規模コードベース | Modules / Entities / Actions / Data / Dependencies の **概観テーブル全列挙** + Mermaid + 深掘り候補リスト |
| **`interactive`** | チームで継続参照、対話的に詳細化 | outline と同じ + Phase 6.5 で利用者指示の深掘りを受付 |

200 ファイル以下のコードベースでは `comprehensive` が自動選択され、200 ファイル超では利用者に選択を促します。

`outline` / `interactive` モードでは、各表セルに **Confidence ラベル** (🟢 VERIFIED / 🟡 INFERRED / 🔴 ASSUMED) が必須付与され、推測と確認済みを明示的に区別します。深掘り候補は 🔴 ASSUMED の多い行、複雑度上位 10%、business-critical キーワード(auth / payment / permission 等) で自動選定されます。

---

## 対応言語と典型単位

`references/inventory-units.md` で以下の言語をカバーしています。

- PHP(Laravel / Symfony / CakePHP 等)
- COBOL(+ JCL)
- Python(Django / Flask / FastAPI 等)
- Java / Kotlin(Spring Boot 等)
- JavaScript / TypeScript(Express / Next.js / NestJS / Expo / React Native / React 等)
- C#(ASP.NET Core 等)
- Go
- **Ruby on Rails**: Controller / Model / Concern / Service / Job / Mailer / Helper / Lib / Migration / Route / View / JS module / config / Mailer template の14単位カタログ

`outline` モード用の概観テーブル定義は `references/outline-tables.md` にあり、Ruby/Rails、Python/Django、JS/TS/React、Go、Java/Kotlin(Spring Boot) の6言語について「どの ripgrep パターンで全列挙するか」を機械化しています。

主要フレームワークについては個別の抽出ガイドを用意しています。

- **Flask**: Blueprint、View function、Hook、Jinja2 テンプレート、Flask-WTF Form、Flask-SQLAlchemy Model、CLI コマンド
- **FastAPI**: APIRouter、Pydantic スキーマ、Dependency、Background Task、Middleware、Exception handler、Security scheme
- **Next.js**(App Router / Pages Router): page / route / layout / Server Action / Middleware、両 Router の混在対応
- **Expo / React Native**: Screen、Navigator、ネイティブモジュール、`app.json` / `eas.json`、パーミッション、Managed / Bare Workflow 判別

加えて、インベントリの **粒度規定** が組み込まれており、最低件数 (`max(50, file_count // 20)`)・マクロ単位禁止比率を Phase 4 検証で機械的にチェックします。

### 機械ソースマップ v2(役割型付き)

`scripts/source_map_v2/` は、フレームワーク対応・**tree-sitter ベース**の抽出器(schema 0.2.0)で、すべてのユニットを5つの普遍テーブル(Modules / Entities / Actions / Data / Dependencies)へ写像し、役割型付け(`endpoint`〔HTTP メソッド+パス付き〕/ `model` / `schema` / `component` / `job` / `route_group` / `migration` / `datastore` …)します。対応は **9言語**: Python、TypeScript/JavaScript、Ruby/Rails、PHP、Java、C#、Go、SQL、COBOL。フレームワーク検出(FastAPI / Django / Flask / Rails / Laravel / Spring / Next.js / Express / NestJS …)で適切なユニット種別を選びます。v1 `source-map.py` と並存し後方互換。tree-sitter は **オプション依存**で、grammar の無い言語はファイルレベル単位＋ loud warning にフォールバックします(黙殺しない)。単体実行:

```bash
python -m source_map_v2 --target <root> --output .cc-rsg/source-map.json
```

未対応言語・フレームワークは利用者要望で随時追加していきます(GitHub Issues)。

---

## テンプレート

初期セットとして以下4種類を同梱しています。

- **Webアプリケーション仕様書** (`templates/web-app.md`)
- **バッチ処理システム仕様書** (`templates/batch-system.md`)
- **APIサービス仕様書** (`templates/api-service.md`)
- **ライブラリ/SDK仕様書** (`templates/library-sdk.md`)

利用者が自前のテンプレートを持参することも可能です。

---

## Question Bank

`cc-rsg` は調査中に湧いた疑問を構造化して `.cc-rsg/questions.json` に蓄積します。

### 7標準カテゴリ

1. **business_rule**(業務ルール)
2. **architecture_decision**(アーキテクチャ判断)
3. **data_model_intent**(データモデル意図)
4. **external_integration**(外部システム連携)
5. **naming_history**(命名・歴史的経緯)
6. **operational_requirement**(運用要件)
7. **security_compliance**(セキュリティ・コンプライアンス)

### 深刻度

- **critical**: この疑問が解消されないと章が書けない
- **important**: 推測で書けるが、確度が低い
- **nice-to-have**: 細部の精緻化に関わる

### 回答不能な疑問

「SMEが退職した」「歴史的経緯を知る人がもういない」など永遠に答えが出ない疑問は `abandoned` としてマークし、最終仕様書の「未確定事項」章に明示的に記載します。

これは仕様書の信頼性を担保する根幹です。

---

## ディレクトリ構造

```
cc-rsg/
├── README.md
├── LICENSE
├── .gitignore
└── skills/
    └── cc-rsg/
        ├── SKILL.md
        ├── agents/
        │   └── chapter-investigator.md  # 章単位サブエージェント定義
        ├── references/
        │   ├── inventory-units.md       # 言語別単位 + 粒度規定 + Rails カタログ
        │   ├── outline-tables.md        # outline モード用の概観テーブル定義(6言語)
        │   ├── template-catalog.md
        │   ├── question-categories.md
        │   ├── verification-checklists.md
        │   └── subagent-prompt.md
        ├── templates/
        │   ├── web-app.md
        │   ├── batch-system.md
        │   ├── api-service.md
        │   └── library-sdk.md
        ├── variants/
        │   └── B/                       # オプションの Context Optimization mode B
        │       ├── README.md            # mode B の使いどころと活性化方法
        │       ├── SKILL.phase3-stepG.md  # Phase 3 STEP G の上書き
        │       └── chapter-investigator.md  # mode B 用 sub-agent(return-value 契約)
        └── scripts/
            ├── source-map.py            # Phase 2: ソースユニット自動抽出 (v1)
            ├── source_map_v2/           # v2: 役割型付き・FW対応・tree-sitter 抽出器 (9言語)
            │   ├── taxonomy.py          #   役割語彙 (5普遍テーブル)
            │   ├── model.py             #   source-map.json schema 0.2.0
            │   ├── detect.py            #   フレームワーク検出 (第1層)
            │   ├── pipeline.py          #   三層オーケストレータ
            │   ├── extractors/          #   言語別エクストラクタ (第2層)
            │   └── tests/               #   受け入れテスト
            ├── build-trace.py           # Phase 3末/Phase 4: [REF:] からの trace.json 生成
            ├── build-traceability.py    # Phase 6: traceability.md 生成
            └── coverage-check.py        # Phase 4: 多項目検証(comprehensive / outline モード対応)
```

---

## 開発状況

現在 **v0.7.0**(source-map v2: 役割型付き・フレームワーク対応・tree-sitter ベースの機械抽出器、9言語対応)。

### 既知の制約

- カスタムカテゴリ追加は手動JSON編集のみ(UI機構は将来拡張)
- MCP統合は未実装(Claude Code 単体動作を前提)
- スラッシュコマンドのオプション(`--restart` 等)は未実装

### ロードマップ(暫定)

- ~~v0.2: 章ファイル命名規約と必須3ファイルの強制化、検証スクリプトに命名チェック追加~~(済)
- ~~v0.2: 章単位サブエージェント delegation、Phase 4 ループバック検証、粒度規定、Rails カタログ、出力言語選択~~(済)
- ~~v0.3: depth モード(comprehensive / outline / interactive)、Phase 6.5 対話深掘りモード、outline-tables.md~~(済)
- ~~v0.4: スキル本体一式の英語ベース化、`output_language` によるバイリンガル出力、README 英語先頭化~~(済)
- ~~v0.5: Mermaid 配色契約(ホストテーマパレット)、`user_custom_deliverables` 強制化、strict `[REF: path:line]` 形式、Phase 5 skip 防止、intent-vs-delivery 監査、Context Optimization mode B(オプション)~~(済)
- ~~v0.6: Phase 0 でのバンドル `.cc-rsg/skill/` への stage、`[REF:]` プレースホルダの整合(先頭 `L` 廃止)、Sources Read カウンタ修正、Ruby トップレベルメソッド抽出~~(済)
- ~~v0.7: `scripts/source_map_v2/` — 役割型付き・フレームワーク対応・tree-sitter ベースの機械ソースマップ(schema 0.2.0)。Python / TS・JS / Ruby・Rails / PHP / Java / C# / Go / SQL / COBOL の言語別エクストラクタ、フレームワーク検出、未対応言語は黙殺せず loud warning、v1 `source-map.py` と並存~~(済)
- v0.8: カスタムカテゴリのUI追加、利用フィードバックを受けたテンプレート追加、Kotlin エクストラクタ、source-map v2 の役割型付けを Phase 2 インベントリへ接続
- v1.0: 数件の実プロジェクト適用後、安定版として公開

---

## プレプリント / Citation

本スキルの設計思想・系譜・実装上の意思決定については以下のプレプリントに詳述しています。論文・発表で言及される場合は引用ください。

> **Preprint**: https://zenodo.org/records/20541685

---

## ライセンス

MIT License。詳細は [LICENSE](LICENSE) を参照。

---

## Contributing

利用フィードバック・テンプレート追加要望・バグ報告は GitHub Issues にて受け付けます。

特に以下の貢献を歓迎します。

- 新しい言語・フレームワークのインベントリ単位定義
- 新しいテンプレート(DWH、機械学習パイプライン、IaC、モバイルアプリ 等)
- 検証チェックリストの拡充
- 実プロジェクト適用例のレポート

---

## 関連プロジェクト

- **cc-sdd**: Spec Driven Development(仕様駆動開発)。`cc-rsg` の対概念
- **Reversa**: 類似OSS。5フェーズパイプライン

---

## 謝辞

設計思想にあたり、以下の先行研究・実装から多大な示唆を受けました。

- KDM(ISO/IEC 19506:2012)を策定した OMG コミュニティ
- Reversa の作者 sandeco 氏
- Siala & Lano (2025) "LLM4Models" 論文
- Thoughtworks の AI 仕様書生成に関するレビュー記事

---

> "綺麗で完成度の高い仕様書よりも、正直で穴が見えている仕様書のほうが実務的価値が高い。"
> — `cc-rsg` 設計原則より

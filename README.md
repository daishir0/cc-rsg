# cc-rsg — Claude Code Reverse Spec Generation

> 既存のコードベースから仕様書を逆生成(リバースエンジニアリング)するための Claude Code スキル

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

## 6フェーズ状態マシン

| Phase | 名称 | 主な動作 |
|-------|------|---------|
| 0 | Setup & Goal | ゴール定義5問で対象範囲・読者・粒度を確定 |
| 1 | Recon & Template | 浅い偵察を行い、仕様書テンプレートを選定 |
| 2 | Plan & WBS | スケルトン生成、インベントリ抽出、WBS分割 |
| 3 | Investigate | 並列サブエージェントで各章ドラフトを生成 |
| 4 | Verify | カバレッジ・整合性・チェックリスト検証 |
| 5 | Refine via Dialogue | Question Bank対話で不確実性を解消 |
| 6 | Deliver | 最終成果物を `.cc-rsg/final/` に出力 |

詳細は [`skills/cc-rsg/SKILL.md`](skills/cc-rsg/SKILL.md) を参照してください。

---

## 対応言語と典型単位

`references/inventory-units.md` で以下の言語をカバーしています。

- PHP(Laravel / Symfony / CakePHP 等)
- COBOL(+ JCL)
- Python(Django / Flask / FastAPI 等)
- Java(Spring 系)
- JavaScript / TypeScript(Express / Next.js / NestJS 等)
- C#(ASP.NET Core 等)

未対応言語は利用者要望で随時追加していきます(GitHub Issues)。

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
        ├── references/
        │   ├── inventory-units.md
        │   ├── template-catalog.md
        │   ├── question-categories.md
        │   ├── verification-checklists.md
        │   └── subagent-prompt.md
        ├── templates/
        │   ├── web-app.md
        │   ├── batch-system.md
        │   ├── api-service.md
        │   └── library-sdk.md
        └── scripts/
            └── coverage-check.py
```

---

## 開発状況

現在 v0.1.0(初版ドラフト)。

### 既知の制約

- カスタムカテゴリ追加は手動JSON編集のみ(UI機構は将来拡張)
- MCP統合は未実装(Claude Code 単体動作を前提)
- スラッシュコマンドのオプション(`--restart` 等)は未実装

### ロードマップ(暫定)

- v0.2: 利用フィードバックを受けてテンプレート追加
- v0.3: カスタムカテゴリのUI追加
- v1.0: 数件の実プロジェクト適用後、安定版として公開

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

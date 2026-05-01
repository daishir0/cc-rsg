# Inventory Units Reference

Phase 2でインベントリ抽出を行う際の、言語・フレームワーク別の典型単位定義集。

このドキュメントは、対象コードベースから「何を全件列挙すべきか」をClaudeが判断するための参照ドキュメントである。Phase 4のインベントリベース検証で「全件カバー」を確認する基準となる。

---

## 共通の考え方

インベントリ単位は以下3階層で考える。

1. **マクロ単位**: モジュール、パッケージ、サービス
2. **ミドル単位**: クラス、関数、エンドポイント、ジョブ
3. **マイクロ単位**: メソッド、フィールド、設定値

仕様書の粒度希望(Phase 0で確定)に応じて、対象とする階層を変える。

- **高レベル概要**: マクロ単位のみ
- **中粒度**: マクロ + ミドル単位
- **詳細**: 全階層

---

## PHP

### マクロ単位
- Composerパッケージ(`composer.json`の`name`)
- 名前空間(PSR-4)
- フレームワーク別モジュール(Laravelの`app/Modules/`, Symfonyの`src/Bundle/`等)

### ミドル単位
- クラス(`class`)、トレイト(`trait`)、インターフェース(`interface`)
- ルート定義(`routes/web.php`, `routes/api.php`、Symfony attributeルート、Slim app->getなど)
- アーティザンコマンド(Laravel `app/Console/Commands/`)
- イベントリスナー、ジョブ、ミドルウェア

### マイクロ単位
- パブリックメソッド
- Eloquent / Doctrineエンティティのプロパティ
- 設定ファイルのキー(`config/*.php`)

### 抽出例
```bash
# クラス列挙
grep -rEn "^(abstract |final )?class [A-Z]" src/ --include="*.php"

# ルート列挙(Laravel)
grep -rEn "Route::(get|post|put|patch|delete|any)" routes/ --include="*.php"

# Artisanコマンド列挙
grep -rEn "protected \\\$signature" app/Console/Commands/ --include="*.php"
```

---

## COBOL

### マクロ単位
- COPYBOOK
- ジョブ(JCLステップ)

### ミドル単位
- PROGRAM-ID
- SECTION
- PARAGRAPH
- CALL対象プログラム(動的・静的)

### マイクロ単位
- 01レベル項目
- ファイル定義(SELECT / FD)
- DB呼び出し(EXEC SQL / EXEC CICS)

### 抽出例
```bash
# PROGRAM-ID列挙
grep -rEn "^[ ]*PROGRAM-ID\\." src/ --include="*.cob" --include="*.cbl"

# SECTION列挙
grep -rEn "^[ 0-9]+[A-Z0-9-]+ +SECTION\\." src/ --include="*.cob"

# CALL文列挙
grep -rEn "^[ ]*CALL +'" src/ --include="*.cob"
```

### COBOL固有の注意
- カラム位置(7列目以降が有効領域、1〜6列はシーケンス番号)に依存する
- COPYBOOK展開後の論理構造と物理ファイルの対応を別途記録する必要がある
- JCL(Job Control Language)はCOBOLとは別言語だが、ジョブ起動条件として仕様書に必須

---

## Python

### マクロ単位
- パッケージ(`__init__.py`を持つディレクトリ)
- モジュール(`.py`ファイル)
- インストール可能パッケージ(`pyproject.toml` / `setup.py`)

### ミドル単位
- クラス(`class`)
- トップレベル関数(`def`)
- FastAPI / Flask / Django のエンドポイント
- Celeryタスク(`@app.task`)
- Click / argparseコマンド

### マイクロ単位
- パブリックメソッド
- Pydanticモデル / dataclassのフィールド
- 設定キー(`settings.py`、環境変数)

### 抽出例
```bash
# クラス列挙
grep -rEn "^class " --include="*.py" src/

# FastAPIエンドポイント
grep -rEn "@(app|router)\\.(get|post|put|patch|delete)" --include="*.py"

# Djangoモデル
grep -rEn "^class .*\\(.*models\\.Model.*\\):" --include="*.py"
```

---

## Java

### マクロ単位
- パッケージ(`com.example.foo`)
- Mavenモジュール(`pom.xml`)
- Springプロファイル / Bundle / OSGi モジュール

### ミドル単位
- クラス(`class`, `interface`, `enum`, `record`)
- Spring `@Controller`, `@Service`, `@Repository`, `@Component`
- エンドポイント(`@RequestMapping`, `@GetMapping`等)
- バッチジョブ(Spring Batch `Job`, `Step`)
- スケジュールタスク(`@Scheduled`)

### マイクロ単位
- パブリックメソッド
- JPA Entity フィールド
- 設定プロパティ(`application.yml` / `application.properties`)

### 抽出例
```bash
# クラス列挙
grep -rEn "^(public |abstract |final )*(class|interface|enum|record) " src/ --include="*.java"

# Spring エンドポイント
grep -rEn "@(Get|Post|Put|Patch|Delete|Request)Mapping" src/ --include="*.java"

# JPAエンティティ
grep -rEn "@Entity" src/ --include="*.java"
```

---

## JavaScript / TypeScript

### マクロ単位
- npmパッケージ(`package.json`の`name`)
- ワークスペース(monorepo: pnpm workspace, turborepo)
- フロントエンド: ページ、ルート(Next.js `app/`, `pages/`)
- バックエンド: モジュール(NestJS)

### ミドル単位
- エクスポートされた関数 / クラス
- Reactコンポーネント、Vueコンポーネント
- Express / Fastify / Hono のルートハンドラ
- NestJS Controller / Service / Module
- バックグラウンドジョブ(BullMQ, Agenda)

### マイクロ単位
- パブリックメソッド
- Zod / Yup / TypeScript型定義
- 環境変数

### 抽出例
```bash
# エクスポート関数 / クラス
grep -rEn "^export (default )?(async )?(function|class|const)" --include="*.ts" --include="*.tsx" --include="*.js" src/

# Express ルート
grep -rEn "(app|router)\\.(get|post|put|patch|delete)\\(" --include="*.ts" --include="*.js" src/

# Reactコンポーネント(関数コンポーネント)
grep -rEn "^export (default )?function [A-Z]" --include="*.tsx" --include="*.jsx" src/
```

---

## C#

### マクロ単位
- アセンブリ(`.csproj`)
- 名前空間(`namespace`)
- ソリューション(`.sln`)

### ミドル単位
- クラス(`class`, `interface`, `record`, `struct`)
- ASP.NET Core Controller / Minimal API エンドポイント
- ホスト型サービス(`IHostedService`)
- バックグラウンドワーカー

### マイクロ単位
- パブリックメソッド
- EF Core エンティティのプロパティ
- `appsettings.json`の設定キー

### 抽出例
```bash
# クラス列挙
grep -rEn "^[[:space:]]*(public |internal )?(abstract |sealed )?(class|interface|record|struct) " src/ --include="*.cs"

# ASP.NET エンドポイント
grep -rEn "\\[Http(Get|Post|Put|Patch|Delete)\\]" src/ --include="*.cs"
```

---

## SQL / データベーススキーマ

ソースコード本体とは別に、データベーススキーマも仕様書の対象になる。

### インベントリ単位
- テーブル
- ビュー
- ストアドプロシージャ / ファンクション
- トリガ
- インデックス
- 外部キー制約

### 抽出方法
- マイグレーションファイル(Rails, Laravel, Django, Flyway, Liquibase)を解析
- 本番DBから`information_schema`を読み取る(可能な場合)
- ER図 / DDLファイルを直接読む

---

## 言語選定が悩ましいケース

### 多言語混在リポジトリ
- 言語ごとに別インベントリを作成し、言語タグを付けて区別する。
- 例: `inventory.json`の各エントリに`"language": "php"`フィールドを追加。

### DSL / 設定ファイルが本質的
- Terraformの`.tf`、Kubernetesの`.yaml`、Ansibleのplaybookなど、DSLが主役のプロジェクトでは、これらをミドル単位として扱う。
- リソース定義(`resource "aws_instance" ...`)、Pod / Service / Deployment、playbookのtaskを単位とする。

### マイクロサービス
- サービス単位をマクロ単位とし、各サービス内の言語別インベントリをミドル単位以下で展開する。

---

## カスタマイズと拡張

利用者が独自の言語 / フレームワーク向けにインベントリ単位を追加したい場合は、このファイルに追記する形で運用する。初版ではUI経由の追加機構は提供しない。

将来的には `references/inventory-units-{custom}.md` のような分割を検討する。

---

## 抽出時のClaudeへの指示要約

1. 対象コードベースの主要言語を特定する(`recon-report.md`から)。
2. 該当言語のセクションを参照し、抽出戦略を立てる。
3. 上記の抽出例を参考に、bash / grep / 言語別ツール(ast-grep, tree-sitter等)で列挙する。
4. 結果を`inventory.json`に保存する。スキーマは SKILL.md の Phase 2 を参照。
5. 抽出時に検出されたコメントアウト・廃止予定コード・テストコードはタグ付けして区別する(`"deprecated": true`等)。

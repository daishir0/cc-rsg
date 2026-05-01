# Inventory Units Reference

Phase 2でインベントリ抽出を行う際の、言語・フレームワーク別の典型単位定義集。

このドキュメントは、対象コードベースから「何を全件列挙すべきか」をClaudeが判断するための参照ドキュメントである。Phase 4のインベントリベース検証で「全件カバー」を確認する基準となる。

<!--
ファイル拡張ガイド:
- 言語追加: ## {言語名} セクションを追加
- フレームワーク固有(L2): 該当言語セクション内に ### {フレームワーク名} 固有 節を追加
- 撤退ライン: 本ファイルが800行を超えた場合、パターンB(言語/フレームワーク2階層構造への分割)への移行を検討すること
-->

## 目次

- [共通の考え方](#共通の考え方)
- [PHP](#php)
- [COBOL](#cobol)
- [Python](#python)
  - [Flask 固有](#flask-固有)
  - [FastAPI 固有](#fastapi-固有)
- [Java](#java)
- [JavaScript / TypeScript](#javascript--typescript)
  - [Next.js 固有(App Router / Pages Router)](#nextjs-固有app-router--pages-router)
  - [Expo / React Native 固有](#expo--react-native-固有)
- [C#](#c)
- [SQL / データベーススキーマ](#sql--データベーススキーマ)
- [言語選定が悩ましいケース](#言語選定が悩ましいケース)
- [カスタマイズと拡張](#カスタマイズと拡張)
- [抽出時のClaudeへの指示要約](#抽出時のclaudeへの指示要約)

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

### Flask 固有

Flask は WSGI アプリケーション、Blueprint によるモジュール分割、デコレータベースのルート定義が特徴。仕様書化では Blueprint 単位での章分割が有効。

#### マクロ単位
- アプリケーションファクトリ関数(`def create_app(): ...`)
- Blueprint(モジュール単位の機能群)
- Flask 拡張(Flask-SQLAlchemy, Flask-Login, Flask-Migrate 等)

#### ミドル単位
- View function(`@app.route` / `@bp.route` / `@app.get` 等)
- Class-based view(`MethodView` 継承クラス)
- Hook(`@app.before_request`, `@app.after_request`, `@app.errorhandler`)
- Jinja2 テンプレート(`templates/*.html`)
- Flask-WTF Form(`FlaskForm` 継承クラス)
- Flask-SQLAlchemy Model(`db.Model` 継承クラス)
- CLI コマンド(`@app.cli.command()` / `@bp.cli.command()`)

#### マイクロ単位
- ルート別の URL パラメータ・クエリパラメータ
- `app.config[...]` の設定キー
- Jinja2 マクロ・フィルタ

#### 抽出例
```bash
# Blueprint 列挙
grep -rEn "Blueprint\\(['\"]" --include="*.py" src/

# ルート定義(app / bp / *_bp)
grep -rEn "@([a-zA-Z_]+)\\.(route|get|post|put|patch|delete)\\(" --include="*.py" src/

# Hook 列挙
grep -rEn "@([a-zA-Z_]+)\\.(before_request|after_request|teardown_request|errorhandler|context_processor)" --include="*.py" src/

# Jinja2 テンプレート
find templates/ -name "*.html" 2>/dev/null

# CLI コマンド
grep -rEn "@([a-zA-Z_]+)\\.cli\\.command\\(" --include="*.py" src/
```

#### Flask 固有の注意
- Blueprint 名は仕様書の章 ID として再利用しやすい
- `before_request` / `after_request` は隠れた業務ロジックを含むため、必ず章に含めること
- アプリケーションファクトリパターンでは設定の差(`config.from_envvar` 等)を運用設定章に明記する

---

### FastAPI 固有

FastAPI は型ヒント駆動の ASGI フレームワーク。Pydantic スキーマと依存性注入(DI)が中心概念で、これらを欠いた仕様書は不完全。

#### マクロ単位
- FastAPI アプリ(`FastAPI()` インスタンス)
- APIRouter(機能単位のルーター)
- Lifespan(`@asynccontextmanager` / `lifespan` パラメータ)

#### ミドル単位
- エンドポイント(`@app.get`, `@router.post` 等、WebSocket 含む)
- Pydantic スキーマ(`BaseModel` 継承クラス、リクエスト / レスポンス両方)
- Dependency(`Depends(...)` で注入される関数 / クラス)
- Background Task(`BackgroundTasks` 経由で実行される関数)
- Middleware(`@app.middleware("http")` / `app.add_middleware(...)`)
- Exception handler(`@app.exception_handler(...)`)
- Security scheme(`OAuth2PasswordBearer`, `APIKeyHeader` 等)

#### マイクロ単位
- パスパラメータ・クエリパラメータの型と制約(`Query(...)`, `Path(...)`)
- Pydantic フィールドのバリデーション(`Field(...)`, `field_validator`)
- レスポンスモデル(`response_model=...`)とステータスコード(`status_code=...`)

#### 抽出例
```bash
# APIRouter 定義
grep -rEn "APIRouter\\(" --include="*.py" src/

# エンドポイント(REST + WebSocket)
grep -rEn "@([a-zA-Z_]+)\\.(get|post|put|patch|delete|head|options|websocket)\\(" --include="*.py" src/

# Pydantic スキーマ
grep -rEn "^class .*\\((BaseModel|RootModel)\\b" --include="*.py" src/

# Dependency 関数
grep -rEn "Depends\\(" --include="*.py" src/

# Exception handler
grep -rEn "@([a-zA-Z_]+)\\.exception_handler\\(" --include="*.py" src/

# Middleware 登録
grep -rEn "@([a-zA-Z_]+)\\.middleware\\(|add_middleware\\(" --include="*.py" src/
```

#### FastAPI 固有の注意
- レスポンス Pydantic スキーマは API 仕様の core であり、テンプレート選定が `api-service` の場合は必ず章として独立させる
- `Depends(...)` で注入される関数は「権限チェック」「DB セッション取得」「外部 API クライアント生成」など重要ロジックを内包することが多い。Question Bank の `architecture_decision` カテゴリで疑問化することを検討
- OpenAPI スキーマ(`/openapi.json`)が自動生成されるため、可能なら起動時に取得して `recon-report.md` に添付すると効率的

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

### Next.js 固有(App Router / Pages Router)

Next.js は規約ベース(convention-over-configuration)のフレームワークで、ファイル名そのものがインベントリ単位になる。App Router(13+)と Pages Router で構造が異なるため、両者を区別すること。

#### マクロ単位
- `app/` ディレクトリ(App Router 採用プロジェクト)
- `pages/` ディレクトリ(Pages Router 採用プロジェクト、`pages/api/` は API エンドポイント)
- Route Group(`(group_name)` 形式のディレクトリ、URL に現れない論理グループ)
- Parallel Route(`@slot_name`)、Intercepting Route(`(.)`, `(..)`, `(...)`)

#### ミドル単位(App Router)
- ページ(`app/**/page.tsx` / `page.ts`)
- レイアウト(`app/**/layout.tsx`)
- ローディング UI(`app/**/loading.tsx`)
- エラー境界(`app/**/error.tsx` / `global-error.tsx`)
- Not Found(`app/**/not-found.tsx`)
- API ルート(`app/**/route.ts` — Route Handler)
- Server Action(`'use server'` を含むファイル / 関数)
- Server Component / Client Component の境界(`'use client'` ディレクティブ)
- Middleware(`middleware.ts`(プロジェクトルート))
- インストルメンテーション(`instrumentation.ts`)

#### ミドル単位(Pages Router)
- ページ(`pages/**/*.tsx`)
- API エンドポイント(`pages/api/**/*.ts`)
- `_app.tsx`, `_document.tsx`, `_error.tsx`(特殊ファイル)
- `getStaticProps` / `getStaticPaths` / `getServerSideProps` を含むページ

#### マイクロ単位
- 動的ルートセグメント(`[id]`, `[...slug]`, `[[...slug]]`)
- ルートメタデータ(`generateMetadata`, `metadata` エクスポート)
- 設定ファイル(`next.config.js` / `next.config.mjs`)
- 環境変数(`NEXT_PUBLIC_*` で始まるものはクライアント露出)

#### 抽出例
```bash
# App Router ページ
find app -name "page.tsx" -o -name "page.ts" -o -name "page.jsx" -o -name "page.js" 2>/dev/null

# App Router API ルート
find app -name "route.ts" -o -name "route.js" 2>/dev/null

# Pages Router ページ(_を除く)
find pages -name "*.tsx" -o -name "*.ts" 2>/dev/null | grep -vE "/(_app|_document|_error)\\."

# Pages Router API
find pages/api -type f 2>/dev/null

# Server Action 含有ファイル
grep -rEn "^[\"']use server[\"']" --include="*.ts" --include="*.tsx" .

# Client Component 宣言
grep -rEn "^[\"']use client[\"']" --include="*.ts" --include="*.tsx" app/

# Middleware
ls middleware.ts middleware.js 2>/dev/null
```

#### Next.js 固有の注意
- **App Router と Pages Router の混在**は実プロジェクトで頻発する。両方検出された場合は仕様書で章を分けること
- Server Action はソースコード上では普通の関数だが、ネットワーク境界を越える。**API エンドポイントとして列挙する**こと
- `'use client'` ディレクティブの有無で実行環境が変わる。セキュリティ・パフォーマンス章で言及対象
- `next.config.js` の `experimental` セクションは将来不安定性の根拠になるため必ず仕様書に明記

---

### Expo / React Native 固有

Expo / React Native は **モバイルアプリ** が出力対象。Web アプリと異なる単位(画面、ナビゲーション、ネイティブモジュール、ビルド構成)が中心になる。テンプレートは `web-app.md` ではなく将来追加予定の `mobile-app.md`(または `web-app.md` をモバイル向けカスタマイズ)を選定すること。

#### マクロ単位
- アプリエントリ(`App.tsx` / `app/_layout.tsx`(Expo Router))
- ナビゲータ階層(Stack / Tab / Drawer の入れ子構造)
- プラットフォーム別ディレクトリ(`android/`, `ios/`、Bare Workflow の場合)

#### ミドル単位
- 画面(Screen)
  - `screens/*.tsx` / `screens/**/*Screen.tsx`(伝統構造)
  - `app/**/*.tsx`(Expo Router 採用、Next.js App Router に類似)
- ナビゲータ定義(`createNativeStackNavigator`, `createBottomTabNavigator`, `createDrawerNavigator`)
- カスタムフック(`hooks/use*.ts`)
- ネイティブモジュール参照(`NativeModules.XXX`, Expo Modules `expo-camera` 等)
- バックグラウンドタスク(`expo-background-fetch`, `expo-task-manager`)
- ストア / 永続化(`AsyncStorage`, `SecureStore`, MMKV, Realm)

#### マイクロ単位
- 画面遷移パラメータの型(`RootStackParamList`)
- パーミッション宣言(`app.json` の `permissions` / `infoPlist` / `androidManifest`)
- 環境変数(`EXPO_PUBLIC_*`、`Constants.expoConfig`)

#### ビルド・配信構成
- `app.json` / `app.config.ts` / `app.config.js`(アプリメタデータ、ビルド設定)
- `eas.json`(EAS Build / Submit 設定、開発 / プレビュー / 本番プロファイル)
- `package.json` の `scripts`(`expo start`, `expo run:ios`, `expo prebuild` 等)
- `metro.config.js`(バンドラ設定)
- `babel.config.js`(プラグイン構成、特に `react-native-reanimated/plugin` 等)

#### 抽出例
```bash
# 画面ファイル(伝統構造)
find . -path ./node_modules -prune -o -name "*Screen.tsx" -print 2>/dev/null

# Expo Router 画面(app/ 配下)
find app -name "*.tsx" -not -name "_*" 2>/dev/null

# ナビゲータ作成
grep -rEn "create(NativeStack|BottomTab|Drawer|Material(Top|Bottom)Tab)Navigator" --include="*.tsx" --include="*.ts" .

# Expo Module 利用
grep -rEn "from ['\"]expo-[a-z-]+['\"]" --include="*.ts" --include="*.tsx" .

# パーミッション宣言(app.json / app.config.*)
grep -nE "(permissions|infoPlist|androidManifest)" app.json app.config.* 2>/dev/null

# EAS ビルドプロファイル
cat eas.json 2>/dev/null | grep -E '"(development|preview|production)"'
```

#### Expo / React Native 固有の注意
- **Managed / Bare Workflow の判別**を最初に行うこと(`android/` `ios/` ディレクトリの有無、または `expo prebuild` の痕跡)。仕様書の構造が大きく変わる
- ネイティブモジュール(`expo-camera`, `expo-location` 等)は **OS 固有のパーミッション** が必要。仕様書のセキュリティ / 運用要件章で必ず言及
- `app.json` の `runtimeVersion` と `eas.json` の `channel` 設定は **OTA(Over-The-Air)アップデート** の挙動を決める。バージョニング章で言及
- **iOS / Android 両プラットフォームで挙動が異なる箇所**(プッシュ通知、バックグラウンド実行、ファイルアクセス)は明示的に章を分けるか節を分けること
- Web 版(`react-native-web`)を出力する設定の有無を確認(出力する場合は Web アプリ章も追加)

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

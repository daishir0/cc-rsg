# Subagent Prompt Reference

Phase 3でTaskツールを介して並列起動するサブエージェントへ渡すプロンプトの完全版テンプレート。

サブエージェントは独立したcontextで動作するため、必要な情報をすべてプロンプトに含める必要がある。一方で、過剰な情報はcontextを圧迫し精度を下げる。本ドキュメントは「必要十分」のラインを定義する。

---

## プロンプト構造

サブエージェントへのプロンプトは以下7セクションで構成する。

1. **役割定義(Role)**
2. **ゴール定義抜粋(Goal Context)**
3. **担当章情報(Chapter Assignment)**
4. **参照すべきインベントリ項目(Inventory)**
5. **作業指示(Task Instructions)**
6. **出力フォーマット(Output Format)**
7. **制約事項(Constraints)**

---

## 完全版プロンプトテンプレート

```
あなたは仕様書の特定章を担当する調査エージェントです。
担当章のドラフトを生成し、メインエージェントに完了報告してください。

================================
[1. 役割定義]
================================
- 役割: 調査エージェント(章ドラフト生成)
- メインエージェント: cc-rsg コーディネータ
- 並列実行されている他エージェント数: {parallel_count}
- 章間の整合性チェックは Phase 4 で別途実施されるため、
  あなたは自分の担当章の精度に集中してください。

================================
[2. ゴール定義抜粋]
================================
- 主たる読者: {primary_reader}
  ({reader_description})
- 読者がこの仕様書を読んだ後にすること: {reader_action}
- 粒度希望: {granularity}
- 重視する観点: {perspectives}
- 既存資料: {existing_docs}

【粒度の解釈ガイド】
- 高レベル概要: マクロ構造のみ。クラス内部のロジックには立ち入らない。
- 中粒度: マクロ + ミドル単位(クラス・関数・エンドポイント)。メソッド単位の詳細は省略可。
- 詳細: 全階層。設定値・しきい値も明記する。

================================
[3. 担当章情報]
================================
- 章ID: {chapter_id}
- 章タイトル: {chapter_title}
- 章の位置づけ(目次内): {chapter_position}
- テンプレート定義(該当章の構造):
{template_section_markdown}

================================
[4. 参照すべきインベントリ項目]
================================
以下のインベントリ項目があなたの担当章で扱うべきものです。
各項目について、ソースコードを精読してください。

{inventory_items_json}

例:
[
  {
    "id": "INV-042",
    "type": "class",
    "name": "UserDeactivationJob",
    "file": "src/jobs/UserDeactivationJob.php",
    "line": 12
  },
  ...
]

================================
[5. 作業指示]
================================
1. 担当インベントリ項目に対応するソースコードを Read ツールで精読する。
2. 必要に応じて Grep / Glob で関連コードを探索する。
3. 章本文を Markdown で生成する。
4. 各記述には [REF: file:lines] 形式で行番号付き参照を付ける。
   - 例: 「ユーザーは退会後30日で物理削除される [REF: src/jobs/UserDeactivationJob.php:34-42]」
5. 不確実性は隠蔽せず、以下マーカーを使用する。
   - [CONFIDENCE: HIGH]   コードから確実に言える
   - [CONFIDENCE: MED]    複数解釈の可能性があるが最有力解釈で記述
   - [CONFIDENCE: LOW]    推測度が高い、要確認
   - [ASK SME]            業務有識者への確認が必要
   - [ASSUMED: {内容}; 根拠: {根拠}]   推測内容と根拠を明示
   - [BLOCKED: see Q-XXX] critical な疑問のため空欄、Question Bank参照
6. 章末尾に「この章で発生した詳細疑問」リストを付与する。
   - 各疑問は以下のフォーマットで記述:
     - Q: {疑問の本文}
     - 根拠: {file:lines コード抜粋}
     - カテゴリ: {7標準カテゴリのいずれか}
     - 深刻度: critical / important / nice-to-have
     - 推測: {現時点の推測内容}

================================
[6. 出力フォーマット]
================================
最終的に以下構造のMarkdownを返してください。

---
chapter_id: {chapter_id}
chapter_title: {chapter_title}
generated_at: {ISO8601}
references_count: {数値}
questions_count: {数値}
blocked_sections: [{section_name}, ...]
---

# {chapter_title}

## (章本文をここに記述)

...

---

## この章で発生した詳細疑問

### Q-XXX (severity: important, category: business_rule)
- 疑問: ...
- 根拠: src/foo.php:34-42
  ```php
  // コード抜粋
  ```
- 推測: ...

### Q-YYY (severity: critical, category: architecture_decision)
...

================================
[7. 制約事項]
================================
- 推測と事実を混同しない。推測には必ず [ASSUMED] マーカーを付ける。
- ゴール定義の粒度を超えた詳細記述はしない(冗長になるため)。
- 担当外のインベントリ項目には言及しない(他エージェントの責務を侵さない)。
- critical な疑問にぶつかった場合は当該節を [BLOCKED] として残し完了報告する。
  全節を完璧に書こうとして停滞するより、書ける節を確実に書いて完了することを優先。
- ファイル全体を Read する前に Grep で関連箇所を絞り込むこと。
  対象ファイルが100行以下の場合は全体 Read で問題ない。
- WebFetch / WebSearch は外部ライブラリの公式ドキュメント参照のみ使用可。
  内部コード探索には使用しない。
- 章本文の長さの目安: 中粒度なら200〜500行、詳細粒度なら500〜1500行。
  これを大幅に超える場合は WBS 分割を見直す必要があるためメインに報告する。

================================
[完了報告]
================================
作業完了時、以下を返してください。
1. 生成した章ドラフト(Markdown)
2. 詳細疑問リスト(構造化)
3. ブロックされた節がある場合、その一覧
4. 想定外の状況に遭遇した場合、その内容
```

---

## プロンプト変数の充填例

メインエージェントは以下の変数をプロンプトに充填してサブエージェントを起動する。

```python
prompt_variables = {
    "parallel_count": 8,
    "primary_reader": "メンテナンス開発者",
    "reader_description": "コードベースを引き継いだ後任エンジニア",
    "reader_action": "コード変更",
    "granularity": "中粒度",
    "perspectives": ["機能正確性", "運用性"],
    "existing_docs": "なし",
    "chapter_id": "ch-04-routes",
    "chapter_title": "ルート / エンドポイント一覧",
    "chapter_position": "第4章 / 全8章中",
    "template_section_markdown": "...(templates/web-app.md の該当章を抜粋)...",
    "inventory_items_json": "[{...}, {...}, ...]"
}
```

---

## サブエージェントの動作モード

サブエージェントの判断ロジックは以下の擬似コードで動作する。

```python
def investigate_chapter(prompt):
    # 1. 担当インベントリ項目をすべて読み込む
    for item in inventory_items:
        read_source(item.file, item.line)

    # 2. 章本文を生成しつつ、疑問が湧いたら記録
    questions = []
    for section in chapter_sections:
        try:
            content = generate_section_content(section)
        except UncertaintyDetected as q:
            questions.append(q)
            if q.severity == "critical":
                content = f"[BLOCKED: see {q.id}]"
            else:
                content = generate_with_assumption(section, q)
                # [CONFIDENCE: LOW; ASSUMED: ...] マーカー付き

    # 3. 章末尾に疑問リストを付与
    return chapter_draft + format_questions(questions)
```

---

## サブエージェントが避けるべき失敗パターン

### パターン1: 章を完璧に書こうとして停滞する
- critical な疑問にぶつかったら [BLOCKED] で残し、書ける節を完成させる。
- 全節を保留して何も書かないのは最悪のパターン。

### パターン2: 推測を事実として書く
- 「おそらく」「と思われる」を地の文に混ぜると、後の読者が事実と推測を区別できない。
- 必ず [CONFIDENCE: LOW] や [ASSUMED] マーカーを使用する。

### パターン3: トレーサビリティ参照を省略する
- 章本文だけ書いて参照を付けないと、後の検証で「根拠不明」となる。
- 1段落に最低1件は [REF:] を入れる。

### パターン4: 担当外まで踏み込む
- 他章のインベントリ項目に詳細言及すると、章間で重複・矛盾が発生する。
- 必要なら「→ 詳細はN章を参照」と書いて済ませる。

### パターン5: ファイルを盲目的に全体Readする
- 大きなファイル(1000行超)を全体Readするとcontextを圧迫する。
- まず Grep で関連箇所を絞り、必要な行範囲だけ Read する。

---

## メインエージェントによるサブエージェント起動コード例

擬似コード(Python風):

```python
from collections import defaultdict

def launch_subagents(wbs, goal, inventory):
    tasks = []
    for chapter in wbs.chapters:
        chapter_inventory = [
            item for item in inventory.items
            if item.id in chapter.assigned_inventory_ids
        ]
        prompt = render_subagent_prompt(
            chapter=chapter,
            goal=goal,
            inventory_items=chapter_inventory,
            parallel_count=len(wbs.chapters)
        )
        task = Task(
            description=f"Investigate chapter: {chapter.title}",
            prompt=prompt,
            subagent_type="general-purpose"
        )
        tasks.append(task)

    # 並列起動
    results = run_in_parallel(tasks)

    # 結果集約
    for result in results:
        save_draft(f"drafts/{result.chapter_id}.md", result.markdown)
        merge_questions(result.questions)
        if result.blocked_sections:
            mark_blocked(result.chapter_id, result.blocked_sections)
```

---

## サブエージェント実行後の品質チェック

メインエージェントは各サブエージェントの結果に対して以下を確認する。

- [ ] フロントマター(`chapter_id`, `chapter_title`, `references_count` 等)が揃っているか
- [ ] `references_count` が0の場合、サブエージェントに再実行を指示する(根拠なし章は不可)
- [ ] `blocked_sections` がある場合、Question Bankに対応エントリが登録されているか
- [ ] 章本文に Markdown構文エラーがないか(コードブロックの閉じ忘れ等)
- [ ] 担当外のインベントリ項目への詳細言及がないか(grep でクロスチェック)

これらの品質チェックに失敗したサブエージェント結果は再実行 or 手動修正対象とする。

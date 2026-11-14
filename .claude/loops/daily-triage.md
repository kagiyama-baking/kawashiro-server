---
name: daily-triage
schedule: "毎日 07:00 JST（cron 0 22 * * * UTC）。Security Scan（JST 0:00）の後に走らせる"
level: L1
checker: "git status --porcelain が空、かつ HEAD が開始時の BASE と同じ（→ run-loop ④）"
report_to: "予定タスクの実行結果（最終メッセージ）と Notion の実行ログ（→ run-loop ⑥）"
connectors: [Notion]
requires: "gh（repo スコープ。Actions の実行結果とコードスキャンの alert を読む）"
limits:
  security_scan_runs: 1      # 読む Security Scan の実行は直近の1回だけ
  ci_runs_per_workflow: 3    # 各ワークフローで一覧に出す実行の数
  failed_log_lines: 60       # 失敗したジョブ1つにつき、ログから読む行数の上限
  stale_days: 7              # PR・Issue がこの日数より長く更新されていなければ「止まっている」
  previous_logs: 1           # 読む前回の実行ログの数
---

# daily-triage — 夜間の Security Scan と CI の仕分け

`run-loop` の手順③で、以下を実行する。共通の枠（開始時の記録・Checker・報告の末尾・実行ログ）は
`.claude/skills/run-loop/SKILL.md` にある。

**L1 なので読むだけ。** コードの変更・コミット・push・PR や Issue の作成とコメント・ワークフローの
再実行や手動実行は一切しない。`git fetch` 以外で作業ツリーとブランチに触れない。

## 手順

### 0. 前回の実行ログを読む

Notion の `DB_Claude 実行ログ`（`collection://4a6bf552-978b-4f2c-88d3-77657e77236f`）から、名前が
`[kawashiro-server] daily-triage ` で始まる行を実行日の新しい順に `limits.previous_logs` 件引き、本文を読む
（`notion-query-data-sources` の SQL → `notion-fetch`）。`[test]` で始まる行は対象外。

- 前回の各項目のキー（下の「項目のキー」）と、初めて出た日（「継続（MM-DD〜）」の日付。無ければその回の実行日）を控える
- 前回の行が無い、または読めないときは全項目を新規として扱い、読めなかったことを「要確認」に書く

### a. Security Scan（イメージごとの CRITICAL/HIGH）

1. 直近の実行を1つ取る。実行中なら、その前の完了した実行を使い、そのことを書く

       gh run list --workflow security-scan.yml -L 2 --json databaseId,status,conclusion,createdAt,url
       gh run view <ID> --json jobs -q '.jobs[]|{name,conclusion,databaseId,steps:[.steps[]|select(.conclusion=="failure")|.name]}'

   - ジョブ `scan-custom (django-api)` と `scan-custom (frontend)` の成否と、落ちたステップを見る
   - **落ちたのが `Scan image` 以外**（`Pull image` など）なら、脆弱性の仕分けはせず、b の CI の失敗として扱う

2. `Scan image` が落ちたジョブは、失敗したステップの表の見出しと件数だけを読む（`limits.failed_log_lines` 行まで）

       gh run view --job <JOB_ID> --log-failed | cut -f3- | grep -E -A2 '^\S+ \((alpine|debian|ubuntu|python-pkg|node-pkg)[^)]*\)$|Total: [0-9]+' | head -n 60

   見出しの括弧（`alpine 3.x` などは OS パッケージ、`python-pkg` などは言語のパッケージ）と、
   `Total: N (HIGH: n, CRITICAL: m)` を控える。

3. 個々の脆弱性はコードスキャンの alert（Security Scan が SARIF で上げたもの）から取る

       gh api 'repos/{owner}/{repo}/code-scanning/alerts?state=open&tool_name=Trivy&per_page=100' --paginate \
         -q '.[]|select(.rule.security_severity_level=="critical" or .rule.security_severity_level=="high")
             |[.most_recent_instance.category, .rule.security_severity_level, .rule.id, .created_at[0:10],
               (.most_recent_instance.message.text|gsub("\n";" | "))]|@tsv'

   `category` がイメージ名、本文の `Package:` `Installed Version:` `Fixed Version:` がパッケージと版。
   **イメージ × パッケージ × 現在の版 × 修正版**でまとめ、CVE は件数と代表の1つだけ書く。

   - イメージごとの件数が 2 の `Total:` と合わないとき、またはそのジョブの `Upload to Security tab` が
     成功していないとき（alert が古い）は、2 の表だけで仕分け、食い違いを「要確認」に書く

4. まとめた各項目を次の3つに分ける

   | 仕分け | 条件 | 書くこと |
   |---|---|---|
   | 待ち | `Fixed Version` が空（表の Status が `affected` / `will_not_fix` など） | パッケージと CVE。修正版が出たら「直せる」に移る |
   | リリース待ち | 修正版があり、develop のイメージ（`:staging`）では直っていて、`:release` に入っていないだけ | 何で直っているか（下の判定のどれか）と、リリースすれば解消すること |
   | 直せる | 修正版があり、develop でもまだ直っていない | OS パッケージなら「ベースイメージの再ビルドで直る（build.yml が OS パッケージを更新する）」。言語のパッケージなら「`<パッケージ> <現在> → <修正版>` に上げる」（`pyproject.toml` に直接書いてあるか、推移的な依存か） |

   develop で直っているかの判定（`git fetch origin develop main` の後に、手元のファイルではなく `origin/*` を読む）:

   - **言語のパッケージ**: `git show origin/develop:django_api/uv.lock`（frontend は `frontend/pnpm-lock.yaml`）の
     版が修正版以上で、`origin/main` の版が修正版未満ならリリース待ち
   - **OS パッケージ**: develop の `build.yml` の最新の成功が、その alert の `created_at` より後で、かつ
     main の `release.yml` の最新の成功より後ならリリース待ち（build.yml の Trivy は修正版のある CRITICAL/HIGH で
     落ちるので、成功したビルドの `:staging` にはその脆弱性が無い）。そうでなければ直せる
   - どちらとも決められないときは推測で埋めず「要確認」に書く

### b. CI（develop と main の直近の実行）

    gh run list --workflow <ファイル> -L 3 --json databaseId,status,conclusion,headBranch,event,createdAt,displayTitle,url

| ワークフロー | 見る実行 |
|---|---|
| `build.yml` | develop の直近 |
| `release.yml` | main の直近 |
| `cleanup-images.yml` | main の直近（毎週日曜） |
| `pr-checks.yml` | 開いている PR ごとの直近。開いた PR が無ければ対象外 |
| `security-scan.yml` | a で見た実行。`Scan image` 以外で落ちたときだけここに書く |

- 成功・実行中は一覧に1行で済ませる
- 失敗は、落ちたジョブとステップを `gh run view <ID> --json jobs` で特定し、そのジョブのログを
  `gh run view --job <JOB_ID> --log-failed | cut -f3- | grep -n -i -E 'error|failed|exit code' | head -n 20`
  で探して、要点を1〜2行で書く。前後を見るときも `limits.failed_log_lines` 行まで
- 直近が成功でも、前回のログで失敗だった項目は「解消」と1行書く

### c. 動きが止まっている PR と Issue

    gh pr list --state open --json number,title,updatedAt,isDraft,reviewDecision,headRefName,url
    gh issue list --state open --json number,title,updatedAt,labels,url

`updatedAt` が `limits.stale_days` 日より前のものを挙げる。どこで止まっているか（レビュー待ち・CI の失敗・
ドラフトのまま など）を、取れた情報の範囲で1行で書く。

### d. 仕分け

a〜c の全項目を「急ぎ／今週中／放置可」に分け、項目ごとに次の一手を1行で書く。

| 区分 | 目安 |
|---|---|
| 急ぎ | CRITICAL の「直せる」。`release.yml` の失敗（本番の入れ替えが止まっている）。`build.yml` の失敗。Security Scan が `Scan image` まで届かない（監視が止まっている） |
| 今週中 | HIGH の「直せる」。「リリース待ち」。開いた PR の `pr-checks.yml` の失敗。`cleanup-images.yml` の失敗。止まっている PR・Issue |
| 放置可 | 「待ち」（CRITICAL の「待ち」は今週中にして、緩和策の要否を「要確認」に書く）。前回からの継続で状況が変わらないもの |

次の一手は、人が行う操作として書く（例: 「develop で build.yml を手動実行 → develop から main へリリース → Security Scan を再実行」）。
このループ自身はそれを行わない。

## 項目のキー（「継続」の判定）

| 種類 | キー |
|---|---|
| 脆弱性 | イメージ × パッケージ × 修正版 |
| CI の失敗 | ワークフロー × ブランチ × ジョブ × ステップ |
| PR・Issue | 番号 |

前回のログに同じキーがあり、仕分けも変わっていなければ「継続（MM-DD〜）」と1行で済ませ、説明を繰り返さない。
仕分けが変わった（直せる → リリース待ち など）、件数が増えた、新しい CVE が加わったときは、その差分だけを書く。
前回あって今回ないものは「解消」と1行書く。

## 制約

- ログの全文を貼らない・読まない。読むのは失敗したステップの、上のコマンドで絞った周辺だけ（`limits.failed_log_lines`）
- 使ってよいのは読み取りの操作だけ: `gh run list` / `gh run view` / `gh pr list` / `gh issue list` /
  `gh api` の GET / `git fetch` / `git show` / `git log` / `git rev-list`。
  **`gh run rerun` `gh workflow run` `gh pr create` `gh issue create` `gh api -X POST|PATCH|PUT|DELETE`、
  `git commit` `git push` `git checkout` `git switch` などは使わない**
- 分からないことは推測で埋めず「要確認」に書く
- gh で Actions やコードスキャンが読めなかったら、推測で報告を作らない。エラーの内容と足りない権限
  （例: コードスキャンの alert は `repo`（非公開リポジトリ）または `security_events` スコープ）を書き、
  判定を ESCALATE_HUMAN にする
- **全部緑で新しい項目も無ければ、本文は「異常なし」の1行だけにして終える**（判定は「新規なし」）。
  全部緑とは、Security Scan の両ジョブ・b の各ワークフローの直近が成功で、止まっている PR・Issue が無いこと

## 報告形式

```
# [kawashiro-server] daily-triage <JST の日付>

急ぎ N / 今週中 N / 放置可 N（新規 N・継続 N・解消 N）

## 急ぎ
- [新規] <項目> — 次の一手: <1行>
- [継続 MM-DD〜] <項目>

## 今週中
## 放置可
## 解消
## 要確認
（無ければ「なし」）

## 詳細
### Security Scan（run <ID>、<実行の JST 日時>、<成否>）
| イメージ | パッケージ | 現在 → 修正版 | 件数（代表の CVE） | 重大度 | 仕分け |

### CI
| ワークフロー | ブランチ | 直近（JST） | 結果 | 失敗箇所・要点 |

### 止まっている PR・Issue
| 番号 | 題 | 最終更新 | 止まっている所 |
```

- 該当のない節は「なし」と書く。埋めるために水増ししない
- 「継続」の項目は「詳細」の表でも1行に縮め、説明を繰り返さない
- 末尾に `run-loop` 共通の「Checker」の節を付ける

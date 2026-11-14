---
name: daily-triage
schedule: "毎日 07:00 JST（cron 0 22 * * * UTC）。Security Scan（JST 0:00）の後に走らせる"
level: L1
checker: "git status --porcelain が空、かつ HEAD が開始時の BASE と同じ（→ run-loop ④）"
report_to: "予定タスクの実行結果（最終メッセージ）と Notion の実行ログ（→ run-loop ⑥）"
notion_loop: "https://app.notion.com/418ddfb6fd8d804bacebcf56ddf88533"  # DB_ループの daily-triage の行（→ run-loop ⑥）
connectors: [Notion]
requires: "gh（Actions の実行・ジョブ・ログと、REST の PR・Issue を読む）。無ければ GitHub コネクタの読み取りのツール（→「GitHub の読み方」）"
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

Notion の `DB_Claude 実行ログ`（`collection://4a6bf552-978b-4f2c-88d3-77657e77236f`）から、「ループ」が
`notion_loop` の行を指している行を、実行日の新しい順に `limits.previous_logs` 件引き、本文を読む
（`notion-query-data-sources` の SQL → `notion-fetch`）。名前が `[test]` で始まる行は対象外。

    SELECT url, "名前", "date:実行日:start" FROM "collection://4a6bf552-978b-4f2c-88d3-77657e77236f"
    WHERE "ループ" LIKE ? AND "名前" NOT LIKE '[test]%'
    ORDER BY "date:実行日:start" DESC LIMIT 1
    -- params: ["%418ddfb6fd8d804bacebcf56ddf88533%"]（notion_loop の末尾の ID。「ループ」はページ URL の JSON 配列）

- 前回の各項目のキー（下の「項目のキー」）と、初めて出た日（「継続（MM-DD〜）」の日付。無ければその回の実行日）を控える
- 前回の行が無い、または読めないときは全項目を新規として扱い、読めなかったことを「要確認」に書く

### a. Security Scan（イメージごとの CRITICAL/HIGH）

1. 直近の実行を1つ取る。実行中なら、その前の完了した実行を使い、そのことを書く

       gh run list --workflow security-scan.yml -L 2 --json databaseId,status,conclusion,createdAt,url
       gh run view <ID> --json jobs -q '.jobs[]|{name,conclusion,databaseId,steps:[.steps[]|select(.conclusion=="failure")|.name]}'

   - ジョブ `scan-custom (django-api)` と `scan-custom (frontend)` の成否と、落ちたステップを見る
   - **落ちたのが `Scan image` 以外**（`Pull image` など）なら、脆弱性の仕分けはせず、b の CI の失敗として扱う

2. `Scan image` が落ちたジョブは、失敗したステップの Trivy の表から、見出しと件数を読む

       gh run view --job <JOB_ID> --log-failed | cut -f3- | sed -E 's/^[0-9T:.-]+Z //' \
         | grep -E -A2 '^\S+ \((alpine|debian|ubuntu|python-pkg|node-pkg)[^)]*\)$|Total: [0-9]+' | head -n 60

   （各行の先頭にタイムスタンプが付くので、`sed` で外してから探す）

   見出しの括弧（`alpine 3.x` などは OS パッケージ、`python-pkg` などは言語のパッケージ）と、
   `Total: N (HIGH: n, CRITICAL: m)` を控える。

3. 同じログの表を、**パッケージ × 重大度 × 状態 × 現在の版 × 修正版**の行にまとめる。ログの全文は読まず、この出力だけを読む

       gh run view --job <JOB_ID> --log-failed | cut -f3- | sed -E 's/^[0-9T:.-]+Z //' \
         | awk -F'│' '
             /^│/ && NF >= 9 {
               for (i = 2; i <= 8; i++) gsub(/^ +| +$/, "", $i)
               if ($2 != "") { lib = $2; sev = $4; st = $5; inst = $6; fix = $7 }
               else { if ($4 != "") sev = $4; if ($5 != "") st = $5; if ($6 != "") inst = $6; if ($7 != "") fix = $7 }
               if ($3 ~ /^(CVE|GHSA)-/) print lib "\t" sev "\t" st "\t" inst "\t" (st == "fixed" ? fix : "") "\t" $3
             }' \
         | awk -F'\t' '{k = $1 "\t" $2 "\t" $3 "\t" $4 "\t" $5; n[k]++; if (!(k in c)) c[k] = $6}
                       END {for (k in n) print k "\t" n[k] "\t" c[k]}' | sort

   出力の列は「パッケージ・重大度・状態・現在の版・修正版・件数・代表の CVE」。Trivy の表は同じ値のセルを
   縦にまとめるので、空のセルは上の行の値を引き継ぐ。状態が `fixed` でなければ修正版は空にする。

   - 件数の合計が 2 の `Total:` と合わないときは、表の読み取りの誤りを疑い、食い違いを「要確認」に書く
   - コードスキャンの alert（SARIF）は使わない。クラウドの実行環境からは権限が無く読めず、表と同じ中身しか持たないため

4. まとめた各項目を次の3つに分ける

   | 仕分け | 条件 | 書くこと |
   |---|---|---|
   | 待ち | `Fixed Version` が空（表の Status が `affected` / `will_not_fix` など） | パッケージと CVE。修正版が出たら「直せる」に移る |
   | リリース待ち | 修正版があり、develop のイメージ（`:staging`）では直っていて、`:release` に入っていないだけ | 何で直っているか（下の判定のどれか）と、リリースすれば解消すること |
   | 直せる | 修正版があり、develop でもまだ直っていない | OS パッケージなら「ベースイメージの再ビルドで直る（build.yml が OS パッケージを更新する）」。言語のパッケージなら「`<パッケージ> <現在> → <修正版>` に上げる」（`pyproject.toml` に直接書いてあるか、推移的な依存か） |

   develop で直っているかの判定（`git fetch origin develop main` の後に、手元のファイルではなく `origin/*` を読む）:

   - **言語のパッケージ**: `git show origin/develop:django_api/uv.lock`（frontend は `frontend/pnpm-lock.yaml`）の
     版が修正版以上で、`origin/main` の版が修正版未満ならリリース待ち
   - **OS パッケージ**: develop の `build.yml` の最新の成功が、1 で取った Security Scan の実行より後で、かつ
     main の `release.yml` の最新の成功より後ならリリース待ち（build.yml の Trivy は修正版のある CRITICAL/HIGH で
     落ちるので、Security Scan より後に成功したビルドの `:staging` にはその脆弱性が無い）。そうでなければ直せる
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

    gh api 'repos/{owner}/{repo}/pulls?state=open&per_page=100' \
      -q '.[]|[.number,.title,.updated_at,.draft,.head.ref,.html_url]|@tsv'
    gh api 'repos/{owner}/{repo}/issues?state=open&per_page=100' \
      -q '.[]|select(.pull_request|not)|[.number,.title,.updated_at,([.labels[].name]|join(",")),.html_url]|@tsv'

（`gh pr list` / `gh issue list` は GraphQL を使い、クラウドの実行環境では 403 になるので、REST で読む）

`updated_at` が `limits.stale_days` 日より前のものを挙げる。どこで止まっているか（レビュー待ち・CI の失敗・
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

## GitHub の読み方

上の手順は gh で書いてある。gh はこのリポジトリのローカルでも、claude.ai の Routine（クラウド）でも使える。
クラウドでは `gh auth status` が「GH_TOKEN が無効」と出るが、REST（Actions の実行・ジョブ・ログ、`gh api` の
PR・Issue）は通る。GraphQL（`gh pr list` など）とコードスキャンの alert は通らない。

gh の REST が通らないときだけ、GitHub コネクタの**読み取り**のツールで代える。

| 手順 | 代わりのツール |
|---|---|
| a1・b の実行の一覧 | `mcp__github__actions_list`（`list_workflow_runs`、`resource_id` にワークフローのファイル名） |
| a1・b のジョブ | `mcp__github__actions_list`（`list_workflow_jobs`、`resource_id` に実行の ID） |
| a2・a3・b のログ | `mcp__github__get_job_logs`（失敗したジョブだけ。出力は上の `sed` / `grep` / `awk` と同じ絞り方で読む） |
| c の PR・Issue | `mcp__github__list_pull_requests` / `mcp__github__list_issues` |

どちらでも Actions の実行・ジョブ・ログが読めなかったら、推測で報告を作らない。エラーの内容と、何が読めなかったかを
書き、判定を ESCALATE_HUMAN にする。PR・Issue だけが読めなかったときは c を「読めなかった」とし、「要確認」に書いて続ける。

## 制約

- ログの全文を貼らない・読まない。読むのは失敗したステップの、上のコマンドで絞った周辺だけ（`limits.failed_log_lines`）
- 使ってよいのは読み取りの操作だけ: `gh run list` / `gh run view` / `gh api` の GET / `git fetch` / `git show` /
  `git log` / `git rev-list`、上の表の GitHub コネクタのツール、Notion の読み取り（`notion-query-data-sources` / `notion-fetch`）。
  **`gh run rerun` `gh workflow run` `gh pr create` `gh issue create` `gh api -X POST|PATCH|PUT|DELETE`、
  `git commit` `git push` `git checkout` `git switch`、GitHub コネクタの書き込みのツール（`actions_run_trigger`
  `create_pull_request` `merge_pull_request` `issue_write` `add_issue_comment` など、作成・更新・実行・マージをするもの）は使わない**
- 分からないことは推測で埋めず「要確認」に書く
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

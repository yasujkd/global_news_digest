# 海外ニュース朝刊ダイジェスト(無料・自動)

日本以外の無料RSS 約40本(経済:米・欧・アジア・中東・国際機関/科学技術:AI・生命科学を優先)を
**月〜土の朝5:30(日本時間)** に自動で集め、1枚のWebページ(+任意でメール/Slack/Discord通知)にまとめます。
GitHub Actions(公開リポジトリなら無料)上で動くので、**Gensparkのクレジットは一切消費しません**。

## セットアップ(約15分・1回だけ)
1. GitHubアカウントを作成 → 新しい **Public** リポジトリを作成(例: `kaigai-news-digest`)
2. このフォルダの中身をすべてアップロード(「Add file → Upload files」。`.github` フォルダも含める)
3. **Settings → Pages** → Source を「Deploy from a branch」、Branch を `main` / `/docs` に設定
   → 数分後 `https://<ユーザー名>.github.io/kaigai-news-digest/` で毎朝のページが見られます
4. **Actions** タブ → 「海外ニュース朝刊」→ **Run workflow** で試運転
5. 以降は自動。過去分は `/archive/YYYY-MM-DD.html` に残ります

## 任意の追加機能(Settings → Secrets and variables → Actions)
| 名前 | 内容 |
|---|---|
| `GEMINI_API_KEY`(Secret) | Google AI Studio の無料APIキー。設定すると **見出しの日本語訳+セクション別3行要約** が付きます(1日8回程度の呼び出しで無料枠内) |
| `SMTP_USER` `SMTP_PASS` `MAIL_TO`(Secret) | メール配信。Gmailなら `SMTP_PASS` に「アプリパスワード」を設定 |
| `DISCORD_WEBHOOK` / `SLACK_WEBHOOK`(Secret) | 完成通知 |
| `PAGE_URL`(Variable) | 通知に載せるページURL |

## 情報源の調整
`feeds.yaml` を編集するだけです。行の追加・削除、`max`(件数)、`weight`(優先度)、
`keywords`(総合ニュース源から経済記事だけを拾うフィルタ)、`priority_keywords`(AI・生命科学の上位表示)を変更できます。
取得失敗したソースはページ末尾に表示されるので、URLの差し替え目安になります。

## 注意
- FT・WSJ・Economist は見出しと抜粋のみ無料(本文は有料)。速報性と論調の把握用です
- 実行時刻はGitHubの混雑で数十分遅れることがあります
- 日曜の朝は実行しません(月曜は土曜朝以降の74時間分をまとめて取得)

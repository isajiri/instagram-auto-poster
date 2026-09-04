# Instagram自動投稿(Notion連携 + GitHub Actions)

Notionの「SNS投稿カレンダー」で予約した投稿を、GitHub Actionsが毎日決まった時刻に
自動でInstagramへ投稿します。**日々の操作はNotionだけ**で完結し、GitHubやコードは
最初の設定だけ触れば、あとは触る必要はありません。

## 1. 日常の使い方(Notion側)

「SNS投稿カレンダー」データベースに新しい行を作り、いつも通り記入するだけです。

- **ステータス** を「自動投稿」にする ← これが自動投稿の合図
- **投稿日付** を設定する(この日以降の実行タイミングで投稿される)
- **プラットフォーム** に「Instagram 📸」を含める
- ページ本文の「元画像」に画像を入れる(「投稿画像」が空、または「元画像と同じ」の場合は
  自動的に「元画像」の画像が使われます)
- 「投稿内容」にキャプション文を書く(この見出し以下、次の見出しまでの文章がそのまま
  Instagramの投稿文になります)

投稿が終わると、そのページの**「チェックボックス」が自動でオンになります**。これが
「投稿済み」の目印です。

※ Instagram Story向け(プラットフォームが「Instagram Story 🎞️」のみの行)は対象外です。
　今回自動化するのはInstagramのフィード/カルーセル投稿のみです。

## 2. 事前準備 (最初の1回だけ)

### 2-1. Notion側の設定

1. https://www.notion.so/my-integrations で「+ New integration」→ 名前を付けて作成
   (例: `instagram-auto-poster`)
2. 作成後に表示される **Internal Integration Secret** をコピーしておく(`NOTION_TOKEN`)
3. Notionで「SNS投稿カレンダー」データベースを開き、右上の「...」→「Connections」→
   作成したインテグレーションを追加(これで初めてAPIから読み書きできるようになります)
4. データベースID: `2c69cfba-b494-8074-bd80-cd658161733f`(確認済み。`NOTION_DATABASE_ID`)

### 2-2. Meta (Instagram Graph API) 側の設定

1. Instagramアカウントが「ビジネス」または「クリエイター」で、Facebookページと
   連携済みであること(確認済み)
2. https://developers.facebook.com/ で開発者アカウント登録 →「アプリを作成」→
   用途は「その他」→ タイプは「ビジネス」
3. 作成したアプリに **Instagram** プロダクトを追加
4. 以下を取得します
   - **Instagramビジネスアカウント ID**(`IG_BUSINESS_ACCOUNT_ID`)
   - 権限 `instagram_basic`, `instagram_content_publish`, `pages_show_list`,
     `pages_read_engagement` を含む **長期(long-lived)アクセストークン**
     (`IG_ACCESS_TOKEN`)
     - 短期トークンをGraph APIエクスプローラーで発行 →
       `GET /oauth/access_token?grant_type=fb_exchange_token&...` で
       60日間有効な長期トークンに交換
     - ⚠️ 長期トークンも60日で失効します。失効前に再発行してGitHub Secretsを
       更新してください

この工程は画面遷移が多いので、詰まったらどの画面で止まっているか教えてください。

## 3. GitHubへのアップロード

このフォルダはまだGitHub上のリポジトリになっていません。GitHubで新しいリポジトリ
(Public/Private どちらでもOK。画像はNotionから直接取得するので、GitHub側の
Public/Privateは投稿処理に影響しません)を作ったら、リポジトリ名を教えてください。

## 4. GitHub Secretsの設定

リポジトリの `Settings` → `Secrets and variables` → `Actions` →
`New repository secret` で以下4つを登録します。

| Name | 値 |
|---|---|
| `NOTION_TOKEN` | 手順2-1で取得したIntegration Secret |
| `NOTION_DATABASE_ID` | `2c69cfba-b494-8074-bd80-cd658161733f` |
| `IG_ACCESS_TOKEN` | 手順2-2で取得した長期アクセストークン |
| `IG_BUSINESS_ACCOUNT_ID` | 手順2-2で取得したInstagramビジネスアカウントID |

## 5. 動作確認

Notionに「ステータス: 自動投稿」「投稿日付: 今日以前」の行を1件用意したら、
GitHubリポジトリの `Actions` タブ →「Instagram自動投稿」→「Run workflow」で
手動実行できます(スケジュール時刻を待たずに即テスト可能)。

## 6. 投稿時刻の変更

`.github/workflows/post.yml` の `cron: "0 8 * * *"` を編集します(UTC基準)。
例: 日本時間20時に投稿したい場合は `cron: "0 11 * * *"`。

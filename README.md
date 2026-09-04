# Instagram自動投稿(GitHub Actions版)

`posts/` フォルダに投稿を置いておくと、GitHub Actionsが毎日決まった時刻に
一番古い(番号が若い)投稿を1件Instagramへ自動投稿します。

## 1. 投稿の追加方法

`posts/` の下に連番のフォルダを作り、画像とキャプションを入れます。

```
posts/
  01_hanabi/
    caption.txt   ← 投稿本文
    1.jpg
    2.jpg
    3.jpg         ← 画像は最大10枚(2枚以上あると自動でカルーセル投稿になる)
  02_ohanami/
    caption.txt
    1.jpg
```

- フォルダ名の頭の連番が投稿順です(`01` → `02` → ...)
- 画像は `.jpg` / `.jpeg` / `.png` に対応
- 投稿が終わると、そのフォルダは自動で `posts_done/` に移動します

## 2. 事前準備 (Meta側)

Instagram公式APIを使うには、以下が必要です。

1. Instagramアカウントが「ビジネス」または「クリエイター」で、Facebookページと連携済みであること(確認済み)
2. https://developers.facebook.com/ で開発者アカウント登録 → 「アプリを作成」→ 用途は「その他」→ タイプは「ビジネス」
3. 作成したアプリに **Instagram** プロダクトを追加
4. Graph APIエクスプローラー、またはアプリの設定画面から以下を取得
   - **Instagramビジネスアカウント ID**(`IG_BUSINESS_ACCOUNT_ID`)
   - 権限 `instagram_basic`, `instagram_content_publish`, `pages_show_list`, `pages_read_engagement` を含む
     **長期(long-lived)アクセストークン**(`IG_ACCESS_TOKEN`)
     - 短期トークンをGraph APIエクスプローラーで発行 → `GET /oauth/access_token?grant_type=fb_exchange_token&...` で60日間有効な長期トークンに交換
     - ⚠️ 長期トークンも60日で失効します。失効前に再発行してGitHub Secretsを更新してください

この工程は画面遷移が多いので、詰まったらどの画面で止まっているか教えてください。一緒に進めます。

## 3. GitHubへのアップロード

このフォルダはまだGitのリポジトリになっていません。GitHub上に新しいリポジトリ(**Public**推奨。画像は
`raw.githubusercontent.com` 経由でInstagramから読み込まれるため、Privateだと投稿画像が取得できません)
を作ったら、教えてください。リポジトリ名が分かればこちらでpushの準備をします。

## 4. GitHub Secretsの設定

リポジトリの `Settings` → `Secrets and variables` → `Actions` → `New repository secret` で以下を登録します。

| Name | 値 |
|---|---|
| `IG_ACCESS_TOKEN` | 手順2で取得した長期アクセストークン |
| `IG_BUSINESS_ACCOUNT_ID` | 手順2で取得したInstagramビジネスアカウントID |

## 5. 動作確認

`posts/` に投稿を1件用意してpushしたら、GitHubリポジトリの `Actions` タブ →
`Instagram自動投稿` → `Run workflow` で手動実行できます(スケジュール時刻を待たずに即テスト可能)。

## 6. 投稿時刻の変更

`.github/workflows/post.yml` の `cron: "0 0 * * *"` を編集します(UTC基準)。
例: 日本時間20時に投稿したい場合は `cron: "0 11 * * *"`。

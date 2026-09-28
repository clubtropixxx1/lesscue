# レスられ総研（lesscue.com）

―私はレス山さんを救いたい―　セックスレスの原因と解消法を、悩みの型ごとに集めたデータベース。

## 仕組み

- 記事と数値の元データは Notion の「セックスレスDB」「セックスレス数字DB」で管理する
- ステータスが「公開」の行だけがサイトに載る（未確認・見送り・博士メモは載らない）
- `tools/build.py` が Notion の書き出しから `index.html` と `data/*.json`、`sitemap.xml` を生成する
- Notion の生データは `_notion/` に置き、Git には入れない（`.gitignore`）

## 更新手順

1. Notion で記事を追加・編集し、載せたいものをステータス「公開」にする
2. Claude に「サイト更新して」と頼む（または週次タスクが自動で実行する）
3. Claude が Notion から書き出し → `python3 tools/build.py` → コミット・プッシュ
4. 数分で lesscue.com に反映される

## ファイル

| パス | 役割 |
| --- | --- |
| `src/template.html` | ページの見た目と動き（診断・絞り込み・数字カード） |
| `tools/build.py` | 生成スクリプト |
| `index.html` | 生成されたページ（直接編集しない） |
| `data/articles.json` `data/stats.json` | 公開中のデータ |
| `CNAME` | 独自ドメイン設定 |

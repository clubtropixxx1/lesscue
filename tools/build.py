#!/usr/bin/env python3
"""レスられ総研 サイト生成スクリプト

Notion から書き出した生データ（_notion/articles.json, _notion/stats.json）を読み、
ステータス「公開」の行だけを使って index.html / data/*.json / sitemap.xml を作る。

_notion/ には未確認の記事や博士メモが含まれるため、Git には入れない（.gitignore 済み）。
公開リポジトリに出るのは、このスクリプトが公開行だけを抜き出した data/ と index.html のみ。

使い方: python3 tools/build.py
"""
import html
import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "_notion"
SITE_URL = "https://lesscue.com/"
# お問い合わせフォームは Web3Forms（https://web3forms.com）。受信用アドレスで発行した Access Key を入れる。
# 公開前提のキーなので HTML に出てよい。空欄のあいだはフォームを隠し、メールアドレスだけ案内する。
FORM_KEY = "91bd222b-3929-41ba-959a-b86b94a19c1a"
CONTACT_EMAIL = "clubtropixxx1@gmail.com"
JST = timezone(timedelta(hours=9))

KIND_COLOR = {
    "悩み": "--t-worry", "解決策": "--t-answer", "体験記": "--t-story",
    "データ・統計": "--t-data", "論文": "--t-paper", "ニュース": "--t-news",
}


def as_list(v):
    """Notion のマルチセレクト／リレーションは JSON 文字列で来るので配列に直す。"""
    if v is None or v == "":
        return []
    if isinstance(v, list):
        return v
    try:
        out = json.loads(v)
        return out if isinstance(out, list) else [out]
    except (ValueError, TypeError):
        return [v]


def stars(v):
    """おすすめ度（☆☆☆／☆☆／☆）を 0〜3 の数に直す。未設定は 0。"""
    return min(3, len(re.findall(r"[☆★]", v or "")))


def rate_html(n):
    if not n:
        return ""
    return (f'<span class="rate" title="おすすめ度 {n}/3" aria-label="おすすめ度 3段階中{n}">'
            + "★" * n + f'<i>{"★" * (3 - n)}</i></span>')


def clean_title(t):
    # 共有時に付くマークダウンの太字記号などを落とす
    return re.sub(r"^\*+|\*+$", "", (t or "").strip())


def load(name):
    p = RAW / name
    if not p.exists():
        return []
    rows = json.loads(p.read_text(encoding="utf-8"))
    return rows.get("results", rows) if isinstance(rows, dict) else rows


def build_articles(rows):
    out = []
    for r in rows:
        if r.get("ステータス") != "公開":
            continue
        url = r.get("userDefined:URL") or ""
        if not url or "yahoo.co.jp" in url:
            continue
        out.append({
            "id": r.get("url", ""),
            "t": clean_title(r.get("タイトル")),
            "u": url,
            "k": r.get("種別") or "未分類",
            "ty": as_list(r.get("型")),
            "tg": as_list(r.get("タグ")),
            "v": r.get("視点") or "",
            "a": as_list(r.get("年代")) or ["不明"],
            "l": r.get("言語") or "日本語",
            "m": r.get("媒体") or "",
            "d": r.get("date:公開日:start") or "",
            "s": r.get("要約") or "",
            "c": r.get("論評") or "",
            "r": stars(r.get("おすすめ度")),
        })
    out.sort(key=lambda x: x["d"], reverse=True)
    return out


def build_stats(rows, article_rows):
    """公開ステータスの数値だけを、男女別の対があれば1枚のカードにまとめる。"""
    by_page = {r.get("url", "").split("?")[0]: r for r in article_rows}
    pub = [r for r in rows if r.get("ステータス") == "公開" and r.get("数値") is not None]
    groups = {}
    for r in pub:
        src = (as_list(r.get("出典記事")) or [""])[0].split("?")[0]
        base = re.sub(r"（(男性|女性|夫|妻)）$", "", r.get("見出し") or "")
        key = (src, r.get("時点"), base)
        groups.setdefault(key, []).append(r)
    cards = []
    for (src, t, base), rs in groups.items():
        art = by_page.get(src, {})
        first_url = next((r.get("出典URL") for r in rs if r.get("出典URL")), "")
        su = first_url or art.get("userDefined:URL", "")
        sm = art.get("媒体", "")
        first = rs[0]
        if len(rs) == 1:
            base = first.get("見出し") or base
        card = {"h": base, "c": first.get("国・地域") or "その他", "t": t or "",
                "o": first.get("対象") or "", "su": su, "sm": sm}
        sexed = [r for r in rs if set(as_list(r.get("区分"))) & {"男性", "女性"}]
        if len(rs) > 1 and len(sexed) == len(rs):
            rs = sorted(rs, key=lambda r: 0 if "男性" in as_list(r.get("区分")) else 1)
            card["br"] = [[as_list(r.get("区分"))[0], r["数値"]] for r in rs]
            parts = [re.match(r"^(.*)の(男性|女性)(.*)$", r.get("対象") or "") for r in rs]
            if all(parts):
                card["o"] = parts[0].group(1) + "（" + "・".join(m.group(2) + m.group(3) for m in parts) + "）"
        else:
            card["v"] = first["数値"]
            card["lb"] = (as_list(first.get("区分")) or ["全体"])[0]
            if first.get("比較前の数値") is not None:
                card["prev"] = [first["比較前の数値"], first.get("比較前の時点") or ""]
        orders = [r.get("表示順") for r in rs if isinstance(r.get("表示順"), (int, float))]
        card["ord"] = min(orders) if orders else None
        card["top"] = any(r.get("TOP掲載") in (True, "__YES__") for r in rs)
        cards.append(card)
    # 表示順が入っているものを小さい順に先に、空欄は調査年の新しい順に後ろへ
    year = lambda c: int(re.sub(r"\D", "", c["t"])[:4] or 0)
    cards.sort(key=lambda c: (c["ord"] is None, c["ord"] if c["ord"] is not None else 0, -year(c)))
    return cards


def static_list(arts):
    """JS が動かない環境や検索エンジン向けに、記事一覧を最初から HTML で書いておく。"""
    if not arts:
        return '<p class="empty">公開中の記事はまだありません。</p>'
    e = html.escape
    items = []
    for d in arts:
        color = KIND_COLOR.get(d["k"], "--t-news")
        lang = "日本語" if d["l"] == "日本語" else d["l"] + "（日本語要約あり）"
        date = d["d"].replace("-", ".") if d["d"] else "公開日不明"
        items.append(
            f'<article class="entry" style="--c:var({color})">'
            f'<div class="meta"><span class="kind">{e(d["k"])}</span>{rate_html(d["r"])}<span>{e(d["m"])}</span><span>{date}</span><span>{e(lang)}</span></div>'
            f'<h5><a href="{e(d["u"])}" target="_blank" rel="noopener">{e(d["t"])}</a></h5>'
            + (f'<p class="comment">{e(d["c"])}</p>' if d["c"] else "")
            + (f'<details><summary>AI要約を読む</summary><p>{e(d["s"])}</p></details>' if d["s"] else "")
            + f'<a class="read" href="{e(d["u"])}" target="_blank" rel="noopener">元の記事を読む ↗</a></article>'
        )
    return '<section class="group"><h4>新しい順</h4><div class="list">' + "".join(items) + "</div></section>"


def js_json(obj):
    return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")


def main():
    article_rows = load("articles.json")
    stat_rows = load("stats.json")
    arts = build_articles(article_rows)
    stats = build_stats(stat_rows, article_rows)
    now = datetime.now(JST)

    (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "data" / "articles.json").write_text(json.dumps(arts, ensure_ascii=False, indent=1), encoding="utf-8")
    (ROOT / "data" / "stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=1), encoding="utf-8")

    tpl = (ROOT / "src" / "template.html").read_text(encoding="utf-8")
    pages = {
        "top": {
            "path": ROOT / "index.html",
            "TITLE": "セックスレスの原因と解消法を型で探す｜レスられ総研",
            "DESCRIPTION": "セックスレスに悩む人のためのデータベース。二択の診断で妻拒否型・夫拒否型などの悩みの型を判定し、原因と解消法の記事・論文・調査データを型別にまとめています。",
            "CANONICAL": SITE_URL,
            "STATIC_LIST": static_list(arts),
            "STATS_HIDDEN": "" if any(c["top"] for c in stats) else " hidden",
        },
        "data": {
            "path": ROOT / "data" / "index.html",
            "TITLE": "数字で見るセックスレス｜割合・調査データまとめ｜レスられ総研",
            "DESCRIPTION": "夫婦のセックスレスの割合や、話し合い・相談の実態など、国内外の調査データを出典つきでまとめています。",
            "CANONICAL": SITE_URL + "data/",
            "STATIC_LIST": "",
            "STATS_HIDDEN": "",
        },
    }
    for mode, pg in pages.items():
        out = (tpl.replace("{{ARTICLES_JSON}}", js_json(arts))
                  .replace("{{STATS_JSON}}", js_json(stats))
                  .replace("{{PAGE_MODE}}", mode)
                  .replace("{{BUILD_DATE}}", now.strftime("%Y.%m.%d"))
                  .replace("{{CONTACT_EMAIL}}", html.escape(CONTACT_EMAIL))
                  .replace("{{FORM_KEY}}", html.escape(FORM_KEY))
                  .replace("{{FORM_HIDDEN}}", "" if FORM_KEY else " hidden")
                  .replace("{{CONTACT_LEAD}}", "下のフォームか" if FORM_KEY else ""))
        for k in ("TITLE", "DESCRIPTION", "CANONICAL", "STATIC_LIST", "STATS_HIDDEN"):
            out = out.replace("{{" + k + "}}", pg[k] if k in ("STATIC_LIST", "STATS_HIDDEN") else html.escape(pg[k]))
        leftover = re.findall(r"\{\{[A-Z_]+\}\}", out)
        if leftover:
            raise SystemExit(f"未置換のプレースホルダ: {leftover}")
        pg["path"].write_text(out, encoding="utf-8")

    (ROOT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"  <url><loc>{SITE_URL}</loc><lastmod>{now.strftime('%Y-%m-%d')}</lastmod></url>\n"
        f"  <url><loc>{SITE_URL}data/</loc><lastmod>{now.strftime('%Y-%m-%d')}</lastmod></url>\n"
        "</urlset>\n", encoding="utf-8")

    print(f"記事 {len(arts)} 件 / 数字カード {len(stats)} 枚 で index.html と data/index.html を生成しました")


if __name__ == "__main__":
    main()

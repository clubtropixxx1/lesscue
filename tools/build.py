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
from urllib.parse import quote
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "_notion"
SITE_URL = "https://lesscue.com/"
# お問い合わせフォームは Web3Forms（https://web3forms.com）。受信用アドレスで発行した Access Key を入れる。
# 公開前提のキーなので HTML に出てよい。空欄のあいだはフォームを隠し、メールアドレスだけ案内する。
FORM_KEY = "91bd222b-3929-41ba-959a-b86b94a19c1a"
CONTACT_EMAIL = "clubtropixxx1@gmail.com"
# 解決のヒントは運営者が記事を読んで付ける。見直しが終わるまではサイトに出さない（True で表示）
SHOW_HINTS = True
JST = timezone(timedelta(hours=9))

KIND_COLOR = {
    "悩み": "--t-worry", "解決策": "--t-answer", "理論": "--t-paper", "体験記": "--t-story",
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


def badge_html(d):
    if d.get("o"):
        return '<span class="own" title="運営者（所長）自身が書いた記事">所長の考察</span>'
    return rate_html(d["r"])


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
            # 解決のヒント：c=夫婦で、w=妻が、m=夫が
            "h": {"c": as_list(r.get("ヒント（夫婦で）")), "w": as_list(r.get("ヒント（妻が）")),
                  "m": as_list(r.get("ヒント（夫が）"))} if SHOW_HINTS else {"c": [], "w": [], "m": []},
            "v": r.get("視点") or "",
            "a": as_list(r.get("年代")) or ["不明"],
            "l": r.get("言語") or "日本語",
            "m": r.get("媒体") or "",
            "d": r.get("date:公開日:start") or "",
            "s": r.get("要約") or "",
            "c": r.get("論評") or "",
            "r": stars(r.get("おすすめ度")),
            # 所長（運営者）自身の記事：☆は付けず「所長の考察」ラベルを出す
            "o": 1 if r.get("所長記事") in (True, "__YES__") else 0,
        })
        a = out[-1]
        # 並び順の重み。所長記事は☆☆と☆の間（外部の☆☆より下、☆より上）
        a["w"] = 1.5 if a["o"] else a["r"]
    # おすすめ度の高い順、同じ重みなら新しい順
    out.sort(key=lambda x: (x["w"], x["d"]), reverse=True)
    return out


def build_stats(rows, article_rows):
    """公開ステータスの数値だけを、男女別の対があれば1枚のカードにまとめる。"""
    # Notion のページURLは /p/ の有無など表記が揺れるので、32桁のページIDで突き合わせる
    pid = lambda u: (re.search(r"[0-9a-f]{32}", (u or "").replace("-", "")) or [""])[0]
    by_page = {pid(r.get("url")): r for r in article_rows}
    pub = [r for r in rows if r.get("ステータス") == "公開" and r.get("数値") is not None]
    groups = {}
    for r in pub:
        src = pid((as_list(r.get("出典記事")) or [""])[0])
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


def static_list(arts, heading="おすすめ順", lite=False):
    """JS が動かない環境や検索エンジン向けに、記事一覧を最初から HTML で書いておく。"""
    if not arts:
        return '<p class="empty">公開中の記事はまだありません。</p>'
    e = html.escape
    items = []
    for d in arts:
        color = KIND_COLOR.get(d["k"], "--t-news")
        lang = "" if d["l"] == "日本語" else f'<span>{e(d["l"])}（日本語要約あり）</span>'
        items.append(
            f'<article class="entry" style="--c:var({color})">'
            f'<div class="meta"><span class="kind">{e(d["k"])}</span>{badge_html(d)}<span>{e(d["m"])}</span>{lang}</div>'
            f'<h5><a href="{e(d["u"])}" target="_blank" rel="noopener">{e(d["t"])}</a></h5>'
            + (f'<p class="comment">{e(d["c"])}</p>' if d["c"] else "")
            + (f'<details><summary>AI要約を読む</summary><p>{e(d["s"])}</p></details>' if d["s"] and not lite else "")
            + f'<a class="read" href="{e(d["u"])}" target="_blank" rel="noopener">元の記事を読む ↗</a></article>'
        )
    if not heading:
        return '<div class="list">' + "".join(items) + "</div>"
    return f'<section class="group"><h4>{heading}</h4><div class="list">' + "".join(items) + "</div></section>"


HWHO = [("c", "夫婦でできること"), ("w", "妻ができること"), ("m", "夫ができること")]


def _pair(h_want, w_want):
    """夫と妻のアイコン。ハートが塗りつぶし＝したい、白抜き＝したくない。"""
    person = ('<svg class="pp {c}" viewBox="0 0 24 40" aria-hidden="true"><circle cx="12" cy="7" r="6"/>'
              '<path d="M2 39v-15a10 10 0 0 1 20 0v15z"/></svg>')
    heart = ('<svg class="hh{on}" viewBox="0 0 24 22" aria-hidden="true"><path d="M12 21s-9-5.6-9-12.2A5 5 0 0 1 12 6a5 5 0 0 1 9 2.8C21 15.4 12 21 12 21z"/></svg>')
    one = lambda c, lab, on: f'<span class="pw">{heart.format(on=" on" if on else "")}{person.format(c=c)}<small>{lab}</small></span>'
    return f'<span class="pair">{one("h", "夫", h_want)}{one("w", "妻", w_want)}</span>'


def quad_html(types, active=None, caption=True):
    """4つの型の図。縦軸＝夫がしたいか、横軸＝妻がしたいか。active の型のマスを強調する。"""
    slug = {t["name"]: t["slug"] for t in types}
    def cell(name, sub, hw, ww, cls=""):
        on = " on" if name == active else ""
        inner = f'{_pair(hw, ww)}<b>{name}</b><span>{sub}</span>'
        if name in slug:
            return f'<a class="qc{cls}{on}" href="/type/{slug[name]}/">{inner}</a>'
        return f'<div class="qc{cls}">{inner}</div>'
    flow_on = " on" if active == "流動的不仲型" else ""
    cap = ('<figcaption>縦軸は「夫がしたいか」、横軸は「妻がしたいか」。ハートが塗りつぶしの人が「したい」側です。'
           'マスを押すと、その型のページが開きます。</figcaption>') if caption else ""
    return ('<figure class="quad"><div class="qwrap">'
            '<div class="qax"><span>▲ 夫はしたい</span></div>'
            '<div class="qgrid">'
            + cell("レスではない", "2人とも求めている", True, True, " ok c1")
            + cell("妻拒否型", "夫は求めているが、妻が応じない", True, False, " c2")
            + '<div class="qhx"><span>◀ 妻はしたい</span><span>妻はしたくない ▶</span></div>'
            + cell("夫拒否型", "妻は求めているが、夫が応じない", False, True, " lo c1")
            + cell("完全不仲型", "2人とも求めず、関係全体が冷えている", False, False, " lo c2")
            + f'<a class="qflow{flow_on}" href="/type/{slug.get("流動的不仲型", "")}/"><b>流動的不仲型</b><span>関係は悪くないがセックスレス</span></a>'
            + '</div><div class="qax qb"><span>▼ 夫はしたくない</span></div>'
            f'</div>{cap}</figure>')


def type_body(t, arts, types):
    """型ページの本文（静的HTML）。検索エンジンが読めるよう、記事一覧もヒントもHTMLで書き出す。"""
    e = html.escape
    hits = [d for d in arts if t["name"] in d["ty"]]
    out = [f'<nav class="crumb" aria-label="現在地"><a href="/">TOP</a> › <a href="/about/#types-def">4つの型</a> › <span>{e(t["name"])}</span></nav>',
           f'<section class="tp-head"><p class="tp-kicker">セックスレスの型</p><h2>{e(t["name"])}</h2>'
           f'<p class="tp-def">{e(t["def"])}</p><p class="tp-count">この型の記事 {len(hits)}件</p></section>']
    out.append(quad_html(types, active=t["name"], caption=False))
    out.append('<p class="tp-cta">自分がどの型か分からない方は → <a href="/#quiz">30秒の簡単診断</a></p>')
    essay = t.get("essay") or []
    body = "".join(f"<p>{e(x)}</p>" for x in essay) if essay else '<p class="soon">所長の解説は準備中です。</p>'
    out.append(f'<section class="tp-sec" id="essay"><h3>所長の解説</h3><div class="greet">{body}'
               '<p class="sign">レスられ総研 所長</p></div></section>')
    cnt = {}
    for d in arts:
        for k in ("c", "w", "m"):
            for h in d["h"][k]:
                cnt[h] = cnt.get(h, 0) + 1
    # 同じヒントが複数の列にあれば「夫婦で」にまとめる（サイトのJSと同じ規則）
    sets = {k: {h for d in arts for h in d["h"][k]} for k in ("c", "w", "m")}
    hg = {}
    for k in ("w", "m"):
        for h in sets[k]:
            hg[h] = "c" if (h in sets["c"] or (h in sets["w"] and h in sets["m"])) else k
    for h in sets["c"]:
        hg[h] = "c"
    groups = []
    for k, label in HWHO:
        hs = sorted({h for d in hits for kk in ("c", "w", "m") for h in d["h"][kk] if hg.get(h) == k}, key=lambda h: (-cnt[h], h))
        if hs:
            chips = "".join(f'<a class="hint" href="/article/?h={quote(h)}">{e(h)}<small>{cnt[h]}</small></a>' for h in hs)
            groups.append(f'<h4 class="cloud-h">{label}</h4><div class="cloud">{chips}</div>')
    if groups:
        out.append('<section class="tp-sec"><h3>この型の解決のヒント</h3>'
                   '<p class="tp-note">この型の記事で紹介されている具体的な行動です。押すと、そのヒントが書かれた記事を一覧で表示します。</p>'
                   + "".join(groups) + "</section>")
    lst = static_list(hits, heading=None) if hits else '<p class="empty">この型の記事は準備中です。</p>'
    out.append(f'<section class="tp-sec"><h3>この型の記事（おすすめ順）</h3>'
               '<p class="tp-note">記事タイトルを押すと、元の記事（外部サイト）が開きます。★は運営が付けたおすすめ度、「AI要約を読む」はAIがまとめた要約です。</p>'
               f'{lst}</section>')
    others = "".join(f'<a href="/type/{o["slug"]}/">{e(o["name"])}</a>' for o in types if o["slug"] != t["slug"])
    out.append(f'<nav class="tp-others" aria-label="ほかの型"><span>ほかの型</span>{others}</nav>')
    return "\n".join(out)


def js_json(obj):
    return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")


def main():
    article_rows = load("articles.json")
    stat_rows = load("stats.json")
    arts = build_articles(article_rows)
    stats = build_stats(stat_rows, article_rows)
    now = datetime.now(JST)

    (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "article").mkdir(exist_ok=True)
    (ROOT / "about").mkdir(exist_ok=True)
    (ROOT / "data" / "articles.json").write_text(json.dumps(arts, ensure_ascii=False, indent=1), encoding="utf-8")
    (ROOT / "data" / "stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=1), encoding="utf-8")

    tpl = (ROOT / "src" / "template.html").read_text(encoding="utf-8")
    pages = {
        "top": {
            "path": ROOT / "index.html",
            "TITLE": "セックスレスの原因と解消法を型で探す｜レスられ総研",
            "DESCRIPTION": "セックスレスに悩む人のためのデータベース。二択の診断で妻拒否型・夫拒否型などの悩みの型を判定し、原因と解消法の記事・論文・調査データを型別にまとめています。",
            "CANONICAL": SITE_URL,
            # TOPはおすすめ上位5件だけ。全件は /article/
            "STATIC_LIST": static_list(arts[:5], heading=None, lite=True),
            "STATS_HIDDEN": "" if any(c["top"] for c in stats) else " hidden",
        },
        "article": {
            "path": ROOT / "article" / "index.html",
            "TITLE": "セックスレスの記事一覧｜原因と解消法を型別に｜レスられ総研",
            "DESCRIPTION": "セックスレスの原因と解消法に関する記事・体験記・論文を、妻拒否型・夫拒否型などの悩みの型や、視点・年代で絞り込んで探せる一覧です。",
            "CANONICAL": SITE_URL + "article/",
            "STATIC_LIST": static_list(arts),
            "STATS_HIDDEN": " hidden",
        },
        "about": {
            "path": ROOT / "about" / "index.html",
            "TITLE": "このサイトについて・所長あいさつ｜レスられ総研",
            "DESCRIPTION": "セックスレスに悩む「レス山さん」のためのデータベース、レスられ総研について。所長あいさつ、4つの型の定義、掲載の基準、免責事項、お問い合わせ。",
            "CANONICAL": SITE_URL + "about/",
            "STATIC_LIST": "",
            "STATS_HIDDEN": " hidden",
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
    types = json.loads((ROOT / "src" / "types.json").read_text(encoding="utf-8"))["types"]
    for t in types:
        n = sum(1 for d in arts if t["name"] in d["ty"])
        pages["type-" + t["slug"]] = {
            "mode": "type",
            "path": ROOT / "type" / t["slug"] / "index.html",
            "TITLE": t["title"], "DESCRIPTION": t["description"],
            "CANONICAL": SITE_URL + f"type/{t['slug']}/",
            "STATIC_LIST": "", "STATS_HIDDEN": " hidden",
            "TYPE_BODY": type_body(t, arts, types),
            "OG_IMAGE": SITE_URL + f"ogp/type-{t['slug']}.png",
            "OG_ALT": f"セックスレスの型：{t['name']}（{t['def']}）｜レスられ総研",
            # 記事も解説もない型ページは中身が薄いので検索エンジンに登録しない
            "ROBOTS": "" if (n or t.get("essay")) else '<meta name="robots" content="noindex">',
        }
        (ROOT / "type" / t["slug"]).mkdir(parents=True, exist_ok=True)
    slugs = {t["name"]: t["slug"] for t in types}
    for mode, pg in pages.items():
        mode = pg.get("mode", mode)
        out = (tpl.replace("{{ARTICLES_JSON}}", js_json(arts))
                  .replace("{{STATS_JSON}}", js_json(stats))
                  .replace("{{PAGE_MODE}}", mode)
                  .replace("{{TYPE_SLUGS}}", js_json(slugs))
                  .replace("{{TYPE_BODY}}", pg.get("TYPE_BODY", ""))
                  .replace("{{ROBOTS}}", pg.get("ROBOTS", ""))
                  .replace("{{OG_IMAGE}}", pg.get("OG_IMAGE", SITE_URL + "ogp.png"))
                  .replace("{{OG_ALT}}", html.escape(pg.get("OG_ALT", "レスられ総研 ―私はレス山さんを救いたい― セックスレスのお悩みと解消法のデータベース")))
                  .replace("{{QUAD_ABOUT}}", quad_html(types) if mode == "about" else "")
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

    day = now.strftime("%Y-%m-%d")
    locs = ["", "article/", "about/", "data/"] + [
        p["CANONICAL"][len(SITE_URL):] for p in pages.values() if p.get("mode") == "type" and not p["ROBOTS"]]
    (ROOT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"  <url><loc>{SITE_URL}{l}</loc><lastmod>{day}</lastmod></url>\n" for l in locs)
        + "</urlset>\n", encoding="utf-8")

    print(f"記事 {len(arts)} 件 / 数字カード {len(stats)} 枚 で TOP・article/・about/・data/・type/（4型）の各ページを生成しました")


if __name__ == "__main__":
    main()

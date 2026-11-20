"""Render the static site from saved data."""
import datetime as dt
import html
import json
import shutil
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import urlparse

from . import affiliates

CAT_ICON = {"Tech": "💻", "Entertainment": "🎬", "Sports": "🏟️", "Business": "📈", "Health": "🩺",
            "Lifestyle": "✨", "Gaming": "🎮", "Science": "🔬", "Home": "🏠", "Politics": "🏛️",
            "World": "🌍", "Crime": "⚖️", "Top Stories": "📰"}


def esc(s):
    return html.escape(str(s if s is not None else ""), quote=True)


def fmt_date(iso):
    d = dt.datetime.fromisoformat(iso)
    return d.strftime("%b %-d, %Y")


def cat_slug(c):
    return c.lower().replace(" ", "-")


class Site:
    def __init__(self, cfg, posts, news, trends, catalog, static_dir, out_dir):
        self.cfg, self.posts, self.news, self.trends = cfg, posts, news, trends
        self.catalog = {p["id"]: p for p in catalog}
        self.catalog_list = catalog
        self.static_dir, self.out = Path(static_dir), Path(out_dir)
        self.site_url = cfg.get("site_url", "").rstrip("/")
        self.base = urlparse(self.site_url).path.rstrip("/")
        self.pages = []  # (path, noindex)
        self.by_topic = {p["topic"].lower(): p for p in reversed(posts)}

    # ---- url helpers ----
    def u(self, path):
        return self.base + path

    def abs(self, path):
        return self.site_url + path

    def monetized(self, p):
        return not p.get("sensitive") and p.get("category") not in self.cfg.get("no_monetize_categories", [])

    # ---- layout ----
    def layout(self, path, title, desc, body, og_type="website", noindex=False, head_extra=""):
        name = self.cfg.get("site_name", "HotTopicHub")
        full_title = title if title == name else f"{title} | {name}"
        ticker = "".join(
            f'<a href="{self.u("/blog/" + self.by_topic[t["topic"].lower()]["slug"] + "/") if t["topic"].lower() in self.by_topic else self.u("/trending/")}">'
            f'<span class="hash">#</span>{esc(t["topic"])}</a>'
            for t in self.trends.get("items", [])[:12])
        robots = '<meta name="robots" content="noindex,follow">' if noindex else ""
        nav = [("/", "Home"), ("/trending/", "Trending"), ("/blog/", "Blog"), ("/news/", "News"), ("/deals/", "Deals")]
        navhtml = "".join(f'<a href="{self.u(h)}"{" class=on" if (h == "/" and path == "/") or (h != "/" and path.startswith(h)) else ""}>{l}</a>' for h, l in nav)
        year = dt.date.today().year
        return f"""<!doctype html>
<html lang="{esc(self.cfg.get('language', 'en'))}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(full_title)}</title>
<meta name="description" content="{esc(desc)}">
{robots}
<link rel="canonical" href="{esc(self.abs(path))}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:type" content="{og_type}">
<meta property="og:url" content="{esc(self.abs(path))}">
<meta property="og:site_name" content="{esc(name)}">
<meta name="twitter:card" content="summary">
<link rel="alternate" type="application/rss+xml" title="{esc(name)}" href="{self.u('/feed.xml')}">
<link rel="stylesheet" href="{self.u('/style.css')}">
{head_extra}
</head>
<body>
<header class="top">
  <div class="wrap bar">
    <a class="logo" href="{self.u('/')}"><span class="pulse"></span>{esc(name)}</a>
    <nav>{navhtml}</nav>
  </div>
  <div class="ticker"><div class="wrap"><span class="live">TRENDING</span><div class="tick-items">{ticker}</div></div></div>
</header>
<main class="wrap">
{body}
</main>
<footer class="foot">
  <div class="wrap">
    <p class="disc">{esc(name)} is a participant in the Amazon Services LLC Associates Program, an affiliate advertising program designed to provide a means for sites to earn advertising fees by advertising and linking to Amazon.com. As an Amazon Associate we earn from qualifying purchases. We also earn commissions from ClickBank offers. <a href="{self.u('/disclosure/')}">Full disclosure</a>.</p>
    <p><a href="{self.u('/about/')}">About</a> · <a href="{self.u('/disclosure/')}">Affiliate disclosure</a> · <a href="{self.u('/privacy/')}">Privacy</a> · <a href="{self.u('/feed.xml')}">RSS</a></p>
    <p class="muted">© {year} {esc(name)}. Articles are written with AI assistance from public trend data and headlines; news links go to the original publishers.</p>
  </div>
</footer>
<script src="{self.u('/app.js')}" defer></script>
</body>
</html>"""

    def write(self, path, content, noindex=False):
        f = self.out / path.lstrip("/")
        if path.endswith("/"):
            f = f / "index.html"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(content, encoding="utf-8")
        if path.endswith("/"):
            self.pages.append((path, noindex))

    # ---- components ----
    def card(self, p, big=False):
        cat = p.get("category", "Lifestyle")
        return f"""<article class="card{' big' if big else ''}">
  <a class="thumb c-{cat_slug(cat)}" href="{self.u('/blog/' + p['slug'] + '/')}"><span>{CAT_ICON.get(cat, '✨')}</span></a>
  <div class="card-body">
    <div class="meta"><a class="cat" href="{self.u('/category/' + cat_slug(cat) + '/')}">{esc(cat)}</a>{f'<span class="heat">🔥 {esc(p["traffic_label"])} searches</span>' if p.get('traffic_label') else ''}</div>
    <h3><a href="{self.u('/blog/' + p['slug'] + '/')}">{esc(p['title'])}</a></h3>
    <p>{esc(p.get('summary', ''))}</p>
    <time datetime="{p['published']}">{fmt_date(p['published'])}</time>
  </div>
</article>"""

    def news_item(self, n):
        return f"""<li class="news-item"><a href="{esc(n['url'])}" target="_blank" rel="nofollow noopener">{esc(n['title'])}</a>
<div class="meta"><span class="src">{esc(n.get('source') or 'News')}</span> · <span class="cat-s">{esc(n.get('category', ''))}</span> · <time datetime="{n['published']}">{fmt_date(n['published'])}</time></div></li>"""

    def amazon_box(self, items, tid=None, heading="Shop the trend"):
        if not items:
            return ""
        cards = "".join(f"""<div class="pick">
  <div class="pick-name">{esc(i['name'])}</div>
  <p>{esc(i.get('why', ''))}</p>
  <a class="btn amz" href="{esc(affiliates.amazon_link(i['search_query'], self.cfg))}" target="_blank" rel="sponsored nofollow noopener">Check price on Amazon →</a>
</div>""" for i in items)
        return f'<section class="shop"><h2>{esc(heading)}</h2><div class="picks">{cards}</div><p class="tiny">Prices and availability change; see Amazon for current details. Paid links.</p></section>'

    def clickbank_box(self, prod, pitch="", tid=None):
        if not prod:
            return ""
        return f"""<aside class="cb">
  <div class="cb-label">Recommended resource</div>
  <h3>{esc(prod['name'])}</h3>
  <p>{esc(pitch or prod.get('description', ''))}</p>
  <a class="btn cbbtn" href="{esc(affiliates.clickbank_link(prod, self.cfg, tid))}" target="_blank" rel="sponsored nofollow noopener">Learn more →</a>
</aside>"""

    # ---- pages ----
    def page_home(self):
        posts = self.posts
        lead = self.card(posts[0], big=True) if posts else '<p class="empty">The first trending posts will appear after the next scheduled run.</p>'
        grid = "".join(self.card(p) for p in posts[1:9])
        chips = "".join(
            f'<a class="chip" href="{self.u("/blog/" + self.by_topic[t["topic"].lower()]["slug"] + "/") if t["topic"].lower() in self.by_topic else self.u("/trending/")}">{esc(t["topic"])} <b>{esc(t["traffic_label"])}</b></a>'
            for t in self.trends.get("items", [])[:10])
        news = "".join(self.news_item(n) for n in self.news[:10])
        picks, seen = [], set()
        for p in posts[:12]:
            if not self.monetized(p):
                continue
            for a in p.get("amazon_products", []):
                if a["search_query"].lower() not in seen:
                    seen.add(a["search_query"].lower())
                    picks.append(a)
                    break
        cb = self.catalog_list[0] if self.catalog_list else None
        body = f"""
<section class="hero">
  <h1>What's trending right now</h1>
  <p class="lede">{esc(self.cfg.get('tagline', ''))}</p>
  <div class="chips">{chips or '<span class="muted">Trends load on the next run.</span>'}</div>
</section>
<div class="cols">
  <div class="main-col">
    {lead}
    <div class="grid">{grid}</div>
    <p><a class="more" href="{self.u('/blog/')}">All articles →</a></p>
  </div>
  <aside class="side">
    <div class="panel"><h2>Latest news</h2><ul class="news-list">{news or '<li class="muted">No headlines yet.</li>'}</ul><a class="more" href="{self.u('/news/')}">More news →</a></div>
    {self.amazon_box(picks[:3], heading="Trending picks") if picks else ''}
    {self.clickbank_box(cb, tid='home') if cb else ''}
  </aside>
</div>"""
        self.write("/", self.layout("/", self.cfg.get("site_name", "HotTopicHub"), self.cfg.get("tagline", ""), body))

    def page_post(self, p):
        path = f"/blog/{p['slug']}/"
        cat = p.get("category", "Lifestyle")
        money = self.monetized(p)
        tid = p["slug"].replace("-", "")[:24]
        disclosure = (f'<p class="disclose">This article contains affiliate links. If you buy through them we may earn a commission at no extra cost to you. <a href="{self.u("/disclosure/")}">Learn more</a>.</p>'
                      if money and (p.get("amazon_products") or p.get("clickbank_product_id")) else "")
        kp = "".join(f"<li>{esc(k)}</li>" for k in p.get("key_points", []))
        srcs = "".join(f'<li><a href="{esc(s["url"])}" target="_blank" rel="nofollow noopener">{esc(s["title"])}</a>{" — " + esc(s["source"]) if s.get("source") else ""}</li>' for s in p.get("sources", []))
        related = [q for q in self.posts if q["slug"] != p["slug"] and q.get("category") == cat][:3] or [q for q in self.posts if q["slug"] != p["slug"]][:3]
        cb = self.catalog.get(p.get("clickbank_product_id")) if money else None
        tags = "".join(f'<span class="tag">#{esc(t)}</span>' for t in p.get("tags", []))
        ld = json.dumps({
            "@context": "https://schema.org", "@type": "NewsArticle", "headline": p["title"],
            "description": p.get("meta_description", ""), "datePublished": p["published"], "dateModified": p["published"],
            "mainEntityOfPage": self.abs(path), "articleSection": cat,
            "publisher": {"@type": "Organization", "name": self.cfg.get("site_name")},
            "author": {"@type": "Organization", "name": self.cfg.get("site_name") + " Staff"},
        })
        body = f"""
<article class="post">
  <nav class="crumbs"><a href="{self.u('/blog/')}">Blog</a> › <a href="{self.u('/category/' + cat_slug(cat) + '/')}">{esc(cat)}</a></nav>
  <h1>{esc(p['title'])}</h1>
  <p class="dek">{esc(p.get('summary', ''))}</p>
  <div class="meta post-meta"><time datetime="{p['published']}">{fmt_date(p['published'])}</time>{f'<span class="heat">🔥 {esc(p["traffic_label"])} searches for “{esc(p["topic"])}”</span>' if p.get('traffic_label') else ''}</div>
  {disclosure}
  {f'<div class="keypoints"><h2>Key points</h2><ul>{kp}</ul></div>' if kp else ''}
  <div class="content">{p['body_html']}</div>
  {self.amazon_box(p.get('amazon_products', []), tid) if money else ''}
  {self.clickbank_box(cb, p.get('clickbank_pitch', ''), tid) if cb else ''}
  {f'<section class="sources"><h2>Coverage &amp; sources</h2><ul>{srcs}</ul></section>' if srcs else ''}
  <div class="tags">{tags}</div>
</article>
{f'<section class="related"><h2>More in {esc(cat)}</h2><div class="grid">{"".join(self.card(q) for q in related)}</div></section>' if related else ''}"""
        head = f'<script type="application/ld+json">{ld}</script>'
        self.write(path, self.layout(path, p["title"], p.get("meta_description", ""), body, "article", p.get("noindex", False), head), p.get("noindex", False))

    def page_list(self, path, title, desc, posts, intro=""):
        body = f'<section class="hero small"><h1>{esc(title)}</h1><p class="lede">{esc(intro or desc)}</p></section>'
        cats = sorted({p.get("category", "Lifestyle") for p in self.posts})
        body += '<div class="chips cats">' + "".join(f'<a class="chip{" on" if path == "/category/" + cat_slug(c) + "/" else ""}" href="{self.u("/category/" + cat_slug(c) + "/")}">{CAT_ICON.get(c, "")} {esc(c)}</a>' for c in cats) + "</div>"
        body += f'<div class="grid three">{"".join(self.card(p) for p in posts[:300]) or "<p class=empty>No posts yet.</p>"}</div>'
        self.write(path, self.layout(path, title, desc, body))

    def page_news(self):
        groups = {}
        for n in self.news:
            groups.setdefault(n.get("category", "Top Stories"), []).append(n)
        order = [f["category"] for f in self.cfg.get("news_feeds", [])]
        sections = ""
        for c in order + [c for c in groups if c not in order]:
            if c not in groups:
                continue
            sections += f'<section class="news-sec" id="{cat_slug(c)}"><h2>{CAT_ICON.get(c, "")} {esc(c)}</h2><ul class="news-list">{"".join(self.news_item(n) for n in groups[c][:15])}</ul></section>'
        jump = "".join(f'<a class="chip" href="#{cat_slug(c)}">{esc(c)}</a>' for c in order if c in groups)
        body = f"""<section class="hero small"><h1>News</h1><p class="lede">Today's top headlines, refreshed automatically. Links open the original publisher.</p><div class="chips">{jump}</div></section>
<div class="cols"><div class="main-col news-cols">{sections or '<p class="empty">No headlines yet.</p>'}</div>
<aside class="side"><div class="panel"><h2>Explained on our blog</h2>{''.join(self.card(p) for p in self.posts[:4])}</div></aside></div>"""
        self.write("/news/", self.layout("/news/", "News", "Today's top headlines across tech, business, sports, entertainment, health and science.", body))

    def page_trending(self):
        rows = ""
        for i, t in enumerate(self.trends.get("items", []), 1):
            post = self.by_topic.get(t["topic"].lower())
            link = f'<a class="btn small" href="{self.u("/blog/" + post["slug"] + "/")}">Read our explainer</a>' if post else ""
            heads = "".join(f'<li><a href="{esc(n["url"])}" target="_blank" rel="nofollow noopener">{esc(n["title"])}</a> <span class="muted">{esc(n.get("source", ""))}</span></li>' for n in t.get("news", [])[:3])
            rows += f'<li class="trend"><div class="rank">{i}</div><div class="tbody"><h3>{esc(t["topic"])} <span class="heat">🔥 {esc(t["traffic_label"])}</span></h3><ul>{heads}</ul>{link}</div></li>'
        upd = f'Updated <time datetime="{self.trends["updated"]}">{fmt_date(self.trends["updated"])}</time>' if self.trends.get("updated") else ""
        body = f'<section class="hero small"><h1>Trending now</h1><p class="lede">The fastest-rising Google searches in the {esc(self.cfg.get("geo", "US"))}. {upd}</p></section><ol class="trends">{rows or "<p class=empty>No trend data yet.</p>"}</ol>'
        self.write("/trending/", self.layout("/trending/", "Trending Now", "The fastest-rising Google searches right now, with the stories behind them.", body))

    def page_deals(self):
        cbs = "".join(self.clickbank_box(p, tid="deals") for p in self.catalog_list)
        seen, picks = set(), []
        for p in self.posts[:40]:
            if not self.monetized(p):
                continue
            for a in p.get("amazon_products", []):
                if a["search_query"].lower() not in seen:
                    seen.add(a["search_query"].lower())
                    picks.append(a)
        body = f"""<section class="hero small"><h1>Deals &amp; picks</h1><p class="lede">Products connected to what people are searching for this week, plus resources we recommend. Paid links: we may earn a commission.</p></section>
{self.amazon_box(picks[:24], 'deals', 'Trending on Amazon') or '<p class="empty">Amazon picks appear here as trending articles are published.</p>'}
<section class="cbgrid"><h2>Recommended resources</h2><div class="cbs">{cbs}</div></section>"""
        self.write("/deals/", self.layout("/deals/", "Deals & Trending Picks", "Products tied to this week's trending topics.", body))

    def page_static(self):
        name, email = esc(self.cfg.get("site_name")), esc(self.cfg.get("contact_email", ""))
        pages = {
            "/about/": ("About", f"<p>{name} tracks the fastest-rising Google searches and explains why they're trending, with links to the original reporting. Articles are drafted with AI assistance from public trend data and headlines.</p><p>Contact: <a href='mailto:{email}'>{email}</a></p>"),
            "/disclosure/": ("Affiliate disclosure", f"<p>{name} is a participant in the Amazon Services LLC Associates Program, an affiliate advertising program designed to provide a means for sites to earn advertising fees by advertising and linking to Amazon.com. As an Amazon Associate we earn from qualifying purchases.</p><p>We also promote digital products through ClickBank and may earn a commission when you buy through those links.</p><p>Affiliate links never change the price you pay. Product suggestions are generated to match each trending topic; always check current prices, reviews and refund terms before buying.</p>"),
            "/privacy/": ("Privacy policy", f"<p>{name} does not require accounts and does not collect personal information directly. When you click an affiliate link, Amazon or ClickBank may set cookies to attribute the referral; their privacy policies apply on their sites. If analytics are added to this site, they will be described here.</p><p>Questions: <a href='mailto:{email}'>{email}</a></p>"),
        }
        for path, (title, html_) in pages.items():
            self.write(path, self.layout(path, title, title, f'<article class="post"><h1>{title}</h1><div class="content">{html_}</div></article>'))
        self.write("/404.html", self.layout("/404.html", "Not found", "Page not found", f'<section class="hero"><h1>Page not found</h1><p><a href="{self.u("/")}">Go to the homepage →</a></p></section>', noindex=True))

    def feeds(self):
        name = esc(self.cfg.get("site_name"))
        items = "".join(f"""<item><title>{esc(p['title'])}</title><link>{esc(self.abs('/blog/' + p['slug'] + '/'))}</link><guid>{esc(self.abs('/blog/' + p['slug'] + '/'))}</guid><pubDate>{format_datetime(dt.datetime.fromisoformat(p['published']))}</pubDate><category>{esc(p.get('category'))}</category><description>{esc(p.get('summary'))}</description></item>"""
                        for p in self.posts[:30])
        (self.out / "feed.xml").write_text(f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>{name}</title><link>{esc(self.abs("/"))}</link><description>{esc(self.cfg.get("tagline"))}</description>{items}</channel></rss>', encoding="utf-8")
        urls = "".join(f"<url><loc>{esc(self.abs(p))}</loc></url>" for p, noidx in self.pages if not noidx)
        (self.out / "sitemap.xml").write_text(f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>', encoding="utf-8")
        (self.out / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {self.abs('/sitemap.xml')}\n", encoding="utf-8")

    def build(self):
        if self.out.exists():
            shutil.rmtree(self.out)
        self.out.mkdir(parents=True)
        for f in self.static_dir.iterdir():
            shutil.copy(f, self.out / f.name)
        (self.out / ".nojekyll").write_text("")
        self.page_home()
        for p in self.posts:
            self.page_post(p)
        self.page_list("/blog/", "Blog", "Explainers on everything trending right now.", self.posts)
        for c in sorted({p.get("category", "Lifestyle") for p in self.posts}):
            ps = [p for p in self.posts if p.get("category") == c]
            self.page_list(f"/category/{cat_slug(c)}/", f"{c}", f"Trending {c.lower()} stories, explained.", ps)
        self.page_news()
        self.page_trending()
        self.page_deals()
        self.page_static()
        self.feeds()
        return len(self.pages)

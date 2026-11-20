"""Turn a trending topic into a blog post, using the Claude API (or a no-AI fallback)."""
import json
import os
import re
import time
import urllib.error
import urllib.request
from html.parser import HTMLParser
import html as htmllib

from . import affiliates

API_URL = "https://api.anthropic.com/v1/messages"
CATEGORIES = ["Tech", "Entertainment", "Sports", "Business", "Health", "Lifestyle",
              "Gaming", "Science", "Home", "Politics", "World", "Crime"]

SYSTEM = """You are the lead writer for a trending-news blog. You write original, genuinely useful
explainers about topics that are trending on Google right now. Rules:
- Write in your own words. Never copy or closely paraphrase news articles; you only get headlines.
- Do not invent facts, quotes, numbers, dates or names. If the headlines don't establish a detail,
  say it is still developing or describe it generally. Prefer background context you are confident about.
- Be clear, specific and readable: short paragraphs, helpful subheadings, no filler, no clickbait.
- Product suggestions must be things a reader of THIS topic would plausibly want. If nothing fits
  naturally, return an empty list. Never suggest products for tragedies, deaths, crimes, disasters
  with victims, or partisan politics; set "sensitive": true for those topics.
- Only recommend a ClickBank offer when the topic is genuinely about that offer's area (e.g. a sleep
  offer for a story about sleep or the time change). Never make health claims about supplements:
  no "cures", "treats", "boosts", guaranteed results or statistics. Describe them neutrally as
  something readers interested in the topic may want to look into.
- Respond with ONLY a single JSON object, no markdown fences."""

PROMPT = """Trending topic (Google Trends, {geo}): "{topic}"
Approximate search volume: {traffic}
Today's date: {date}

Recent headlines about it:
{headlines}

ClickBank offers available to recommend (use the id, or null if none truly fits):
{catalog}

Return JSON with exactly these keys:
{{
  "skip": false,                  // true only if the topic is unclear, adult, or unsafe to write about
  "sensitive": false,             // true for deaths, tragedies, crime, disasters with victims, partisan politics
  "category": "one of {categories}",
  "title": "SEO headline, max 70 chars, no clickbait",
  "meta_description": "max 155 chars",
  "summary": "1-2 sentence dek shown under the headline",
  "key_points": ["3 to 5 short takeaways"],
  "body_html": "650-1000 words of HTML using only <h2>, <h3>, <p>, <ul>, <ol>, <li>, <strong>, <em>, <blockquote>. Suggested flow: what's happening, why it's trending now, background, what it means for readers, what to watch next.",
  "amazon_products": [{{"name": "short product label", "search_query": "amazon search phrase", "why": "one sentence"}}],
  "clickbank_product_id": null,
  "clickbank_pitch": "one honest sentence on why this offer is relevant, or empty",
  "tags": ["3-6 lowercase tags"]
}}
amazon_products: 0-4 items, empty if sensitive."""


# ---------- HTML sanitising ----------
ALLOWED = {"h2", "h3", "p", "ul", "ol", "li", "strong", "em", "blockquote", "br", "a"}


class _Sanitizer(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "iframe"):
            self.skip += 1
            return
        if tag not in ALLOWED:
            return
        if tag == "a":
            href = dict(attrs).get("href", "")
            if not href.startswith(("http://", "https://")):
                return
            self.out.append(f'<a href="{htmllib.escape(href)}" rel="nofollow noopener" target="_blank">')
        else:
            self.out.append(f"<{tag}>")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "iframe"):
            self.skip = max(0, self.skip - 1)
            return
        if tag in ALLOWED and tag != "br":
            self.out.append(f"</{tag}>")

    def handle_data(self, data):
        if self.skip:
            return
        self.out.append(htmllib.escape(data, quote=False))


def sanitize(html_in):
    s = _Sanitizer()
    s.feed(html_in or "")
    s.close()
    return "".join(s.out)


# ---------- Claude API ----------
def call_claude(system, prompt, cfg, api_key, retries=4):
    body = json.dumps({
        "model": cfg["ai"].get("model", "claude-sonnet-5-5"),
        "max_tokens": cfg["ai"].get("max_tokens", 4000),
        "system": system,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    for attempt in range(retries):
        req = urllib.request.Request(API_URL, data=body, headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=240) as r:
                data = json.load(r)
            return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="ignore")[:300]
            if e.code in (429, 500, 502, 503, 529) and attempt < retries - 1:
                time.sleep(10 * (attempt + 1))
                continue
            raise RuntimeError(f"Claude API error {e.code}: {msg}")


def extract_json(text):
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < 0:
        raise ValueError("no JSON object in model output")
    return json.loads(text[start:end + 1])


def ai_post(trend, cfg, catalog, api_key, today):
    headlines = "\n".join(f"- {n['title']} ({n.get('source') or 'news'})" for n in trend["news"][:6]) or "- (no headlines available)"
    cat_lines = "\n".join(f"- {p['id']}: {p['name']} [{p.get('category', '')}] {p.get('description', '')}" for p in catalog) or "- (none)"
    prompt = PROMPT.format(geo=cfg.get("geo", "US"), topic=trend["topic"], traffic=trend.get("traffic_label") or "unknown",
                           date=today, headlines=headlines, catalog=cat_lines, categories=", ".join(CATEGORIES))
    raw = call_claude(SYSTEM, prompt, cfg, api_key)
    d = extract_json(raw)
    if d.get("skip"):
        return None
    ids = {p["id"] for p in catalog}
    cb = d.get("clickbank_product_id")
    return {
        "title": str(d.get("title") or trend["topic"])[:110],
        "meta_description": str(d.get("meta_description") or d.get("summary") or "")[:160],
        "summary": str(d.get("summary") or ""),
        "category": d.get("category") if d.get("category") in CATEGORIES else "Lifestyle",
        "sensitive": bool(d.get("sensitive")),
        "key_points": [str(k) for k in (d.get("key_points") or [])][:5],
        "body_html": sanitize(d.get("body_html", "")),
        "amazon_products": [
            {"name": str(p.get("name", ""))[:80], "search_query": str(p.get("search_query", ""))[:100], "why": str(p.get("why", ""))[:200]}
            for p in (d.get("amazon_products") or []) if p.get("search_query")
        ][:4],
        "clickbank_product_id": cb if cb in ids else None,
        "clickbank_pitch": str(d.get("clickbank_pitch") or ""),
        "tags": [str(t).lower() for t in (d.get("tags") or [])][:6],
        "ai": True,
        "noindex": False,
    }


def fallback_post(trend, cfg, catalog):
    """No API key: publish a short curated roundup (marked noindex so thin pages don't hurt SEO)."""
    topic = trend["topic"]
    items = "".join(
        f'<li><a href="{htmllib.escape(n["url"])}" rel="nofollow noopener" target="_blank">{htmllib.escape(n["title"])}</a>'
        f'{" (" + htmllib.escape(n["source"]) + ")" if n.get("source") else ""}</li>'
        for n in trend["news"][:6])
    body = (f"<p><strong>{htmllib.escape(topic.title())}</strong> is one of today's top searches"
            f"{' with ' + htmllib.escape(trend['traffic_label']) + ' searches' if trend.get('traffic_label') else ''}. "
            "Here's the coverage driving the interest.</p>"
            f"<h2>Latest coverage</h2><ul>{items or '<li>Coverage is still coming in.</li>'}</ul>")
    text = topic + " " + " ".join(n["title"] for n in trend["news"])
    cb = affiliates.match_clickbank(text, catalog)
    return {
        "title": f"Why “{topic.title()}” Is Trending Right Now",
        "meta_description": f"What's behind today's spike in searches for {topic}, with the latest coverage.",
        "summary": f"A quick look at the stories pushing {topic} up the charts today.",
        "category": "Lifestyle",
        "sensitive": False,
        "key_points": [],
        "body_html": body,
        "amazon_products": [],
        "clickbank_product_id": cb["id"] if cb else None,
        "clickbank_pitch": cb.get("description", "") if cb else "",
        "tags": [topic.lower()],
        "ai": False,
        "noindex": True,
    }


def write_post(trend, cfg, catalog, today, use_ai=True):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if use_ai and key:
        try:
            return ai_post(trend, cfg, catalog, key, today)
        except Exception as e:
            print(f"[warn] AI writing failed for '{trend['topic']}': {e}; using fallback")
    return fallback_post(trend, cfg, catalog)

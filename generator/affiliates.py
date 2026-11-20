"""Affiliate link builders and product matching.

Links are generated at render time from stored search queries / product ids,
so changing your Amazon tag or ClickBank nickname in config.json updates every
page on the next build.
"""
import re
from urllib.parse import urlencode, urlparse, parse_qsl, urlunparse


def amazon_link(query, cfg):
    a = cfg["amazon"]
    return f"https://{a.get('domain', 'www.amazon.com')}/s?" + urlencode({"k": query, "tag": a["tag"]})


def _tid(s):
    # ClickBank tracking IDs: keep them short and alphanumeric
    return re.sub(r"[^A-Za-z0-9]", "", s or "")[:24]


def clickbank_link(product, cfg, tid=None):
    tid = _tid(tid)
    if product.get("hoplink"):
        url = product["hoplink"]
        if tid:
            p = urlparse(url)
            q = dict(parse_qsl(p.query))
            q["tid"] = tid
            url = urlunparse(p._replace(query=urlencode(q)))
        return url
    params = {"affiliate": cfg["clickbank"]["affiliate_id"], "vendor": product["vendor"]}
    if tid:
        params["tid"] = tid
    return "https://hop.clickbank.net/?" + urlencode(params)


def match_clickbank(text, catalog, category=None):
    """Return the best keyword-matching ClickBank product, or None."""
    text = " " + re.sub(r"[^a-z0-9 ]", " ", (text or "").lower()) + " "
    best, best_score = None, 0
    for p in catalog:
        score = sum(2 for k in p.get("keywords", []) if f" {k.lower()} " in text)
        if category and p.get("category") == category:
            score += 1
        if score > best_score:
            best, best_score = p, score
    return best if best_score >= 2 else None

"""Fetch trending topics (Google Trends RSS) and news headlines (Google News RSS)."""
import datetime as dt
import time
import urllib.error
import email.utils
import html
import re
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

UA = "Mozilla/5.0 (compatible; TrendSiteBot/1.0; +https://github.com)"
TRENDS_URL = "https://trends.google.com/trending/rss?geo={geo}"


def now_iso():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def fetch(url, timeout=25, retries=3):
    for attempt in range(retries):
        req = urllib.request.Request(url, headers={
            "User-Agent": UA,
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
        })
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < retries - 1:
                time.sleep(15 * (attempt + 1))  # rate limited: back off and retry
                continue
            raise


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def _text(el, name):
    for c in el:
        if _local(c.tag) == name:
            return (c.text or "").strip()
    return ""


def _date(s):
    try:
        d = email.utils.parsedate_to_datetime(s)
        if d.tzinfo is None:
            d = d.replace(tzinfo=dt.timezone.utc)
        return d.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat()
    except Exception:
        return now_iso()


def traffic_to_int(label):
    m = re.match(r"([\d.,]+)\s*([KkMm]?)", label or "")
    if not m:
        return 0
    n = float(m.group(1).replace(",", ""))
    mult = {"k": 1_000, "m": 1_000_000}.get(m.group(2).lower(), 1)
    return int(n * mult)


def parse_trends(xml_bytes):
    root = ET.fromstring(xml_bytes)
    out = []
    for item in root.iter("item"):
        title = html.unescape(_text(item, "title"))
        if not title:
            continue
        news = []
        for c in item:
            if _local(c.tag) == "news_item":
                t = html.unescape(_text(c, "news_item_title"))
                u = _text(c, "news_item_url")
                if t and u.startswith("http"):
                    news.append({"title": t, "url": u, "source": _text(c, "news_item_source")})
        label = _text(item, "approx_traffic")
        out.append({
            "topic": title,
            "traffic_label": label,
            "traffic": traffic_to_int(label),
            "published": _date(_text(item, "pubDate")),
            "news": news,
        })
    return out


def parse_news(xml_bytes, category, limit):
    root = ET.fromstring(xml_bytes)
    out = []
    for item in root.iter("item"):
        title = html.unescape(_text(item, "title"))
        link = _text(item, "link")
        source = html.unescape(_text(item, "source"))
        if source and title.endswith(" - " + source):
            title = title[: -(len(source) + 3)]
        if not title or not link.startswith("http"):
            continue
        out.append({
            "title": title.strip(),
            "url": link,
            "source": source,
            "category": category,
            "published": _date(_text(item, "pubDate")),
        })
        if len(out) >= limit:
            break
    return out


def get_trends(geo, fixtures=None):
    try:
        raw = (Path(fixtures) / "trends.xml").read_bytes() if fixtures else fetch(TRENDS_URL.format(geo=geo))
        return parse_trends(raw)
    except Exception as e:
        print(f"[warn] trends fetch failed: {e}")
        return []


def get_news(feeds, per_feed, fixtures=None):
    items = []
    for i, f in enumerate(feeds):
        try:
            if fixtures:
                p = Path(fixtures) / f"news_{i}.xml"
                if not p.exists():
                    continue
                raw = p.read_bytes()
            else:
                if i:
                    time.sleep(4)  # be polite to Google News; rapid requests get rate-limited
                raw = fetch(f["url"])
            items.extend(parse_news(raw, f["category"], per_feed))
        except Exception as e:
            print(f"[warn] news feed '{f['category']}' failed: {e}")
    return items

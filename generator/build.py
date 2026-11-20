"""Main entry point.

    python -m generator.build                # fetch trends + news, write new posts, render site
    python -m generator.build --render-only  # just rebuild HTML from saved data
    python -m generator.build --offline      # use sample feeds in fixtures/ (for testing)
    python -m generator.build --no-ai        # skip the Claude API (fallback roundups)
"""
import argparse
import datetime as dt
import json
import re
import unicodedata
from pathlib import Path

from . import sources, writer, render

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def load(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save(path, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, indent=1, ensure_ascii=False), encoding="utf-8")


def slugify(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s[:70].rstrip("-") or "post"


def norm(s):
    return set(re.sub(r"[^a-z0-9 ]", " ", s.lower()).split())


def recently_covered(topic, posts, days):
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
    words = norm(topic)
    for p in posts:
        if dt.datetime.fromisoformat(p["published"]) < cutoff:
            continue
        other = norm(p["topic"])
        if words == other or (words and len(words & other) / len(words | other) >= 0.6):
            return True
    return False


def merge_news(old, new, keep):
    seen, out = set(), []
    for n in sorted(new + old, key=lambda x: x["published"], reverse=True):
        key = n["url"]
        tkey = n["title"].lower()[:60]
        if key in seen or tkey in seen:
            continue
        seen.update({key, tkey})
        out.append(n)
    return out[:keep]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--render-only", action="store_true")
    ap.add_argument("--offline", action="store_true", help="read sample feeds from fixtures/")
    ap.add_argument("--no-ai", action="store_true")
    ap.add_argument("--posts", type=int, help="override posts_per_run")
    args = ap.parse_args()

    cfg = load(ROOT / "config.json", {})
    catalog = load(ROOT / "clickbank_products.json", {}).get("products", [])
    posts = load(DATA / "posts.json", [])
    news = load(DATA / "news.json", [])
    trends = load(DATA / "trends.json", {"updated": None, "items": []})

    if not args.render_only:
        fixtures = ROOT / "fixtures" if args.offline else None
        fresh_trends = sources.get_trends(cfg.get("geo", "US"), fixtures)
        if fresh_trends:
            trends = {"updated": sources.now_iso(), "items": fresh_trends}
        fresh_news = sources.get_news(cfg.get("news_feeds", []), cfg.get("news_per_feed", 12), fixtures)
        news = merge_news(news, fresh_news, cfg.get("news_keep", 300))
        print(f"trends: {len(fresh_trends)}  news fetched: {len(fresh_news)}  news kept: {len(news)}")

        budget = args.posts if args.posts is not None else cfg.get("posts_per_run", 3)
        today = dt.date.today().isoformat()
        slugs = {p["slug"] for p in posts}
        candidates = sorted(fresh_trends, key=lambda t: t["traffic"], reverse=True)
        for t in candidates:
            if budget <= 0:
                break
            if t["traffic"] < cfg.get("min_traffic", 0):
                continue
            if recently_covered(t["topic"], posts, cfg.get("skip_recently_covered_days", 5)):
                print(f"  skip (recently covered): {t['topic']}")
                continue
            print(f"  writing: {t['topic']} ({t['traffic_label']})")
            post = writer.write_post(t, cfg, catalog, today, use_ai=not args.no_ai)
            if not post:
                print("    model chose to skip this topic")
                continue
            slug = base = slugify(post["title"])
            i = 2
            while slug in slugs:
                slug, i = f"{base}-{i}", i + 1
            slugs.add(slug)
            post.update({
                "slug": slug,
                "topic": t["topic"],
                "traffic_label": t["traffic_label"],
                "published": sources.now_iso(),
                "sources": t["news"][:6],
            })
            posts.insert(0, post)
            budget -= 1

        save(DATA / "posts.json", posts)
        save(DATA / "news.json", news)
        save(DATA / "trends.json", trends)

    n = render.Site(cfg, posts, news, trends, catalog, ROOT / "static", ROOT / "site").build()
    print(f"rendered {n} pages -> site/")


if __name__ == "__main__":
    main()

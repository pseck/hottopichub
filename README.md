# HotTopicHub: an automated trending-topics affiliate site

Every 6 hours this site updates itself without you:

1. Pulls the fastest-rising searches from **Google Trends** (Trending Now RSS) plus headlines from **Google News**.
2. Picks the biggest topics it hasn't covered recently and has **Claude** write an original explainer for each one.
3. Attaches **Amazon** product picks (search links with your Associates tag) and a matching **ClickBank** offer (HopLink with your nickname and a per-post tracking ID).
4. Rebuilds the site (Home, Trending, Blog, News, Deals, category pages, RSS, sitemap) and publishes it to **GitHub Pages**, for free.

No server and no database. Python standard library only, so nothing to install.

---

## One-time setup (about 15 minutes)

### 1. Put the code on GitHub
Create a new **public** repository (e.g. `trendsite`) and upload everything in this folder, including the hidden `.github` folder.

### 2. Edit `config.json`
| Setting | What to put |
|---|---|
| `site_name`, `tagline`, `contact_email` | Your brand |
| `site_url` | `https://YOUR-USERNAME.github.io/trendsite` (or your custom domain, e.g. `https://hottopichub.com`) |
| `amazon.tag` | Your Amazon Associates tracking ID, e.g. `mysite-20` |
| `clickbank.affiliate_id` | Your ClickBank account nickname |
| `posts_per_run` | New articles per run. 3 posts × 4 runs = 12 posts a day |
| `geo` | Country for trends: `US`, `GB`, `CA`, `AU`, … |

### 3. Add your ClickBank offers to `clickbank_products.json`
The four entries in it are **placeholders**. Replace them with real offers from the ClickBank marketplace: `vendor` is the seller's nickname, and `keywords` decide which trending posts an offer can appear on. Claude picks the best fit per article, or none if nothing fits.

### 4. Add your Claude API key
Get a key at console.anthropic.com. In your repo, go to **Settings → Secrets and variables → Actions → New repository secret**:
- Name: `ANTHROPIC_API_KEY`
- Value: your key

Cost is roughly 1–3 cents per article on Sonnet. Set `"model": "claude-haiku-5-5"` in `config.json` to make it cheaper.

### 5. Turn on GitHub Pages
**Settings → Pages → Build and deployment → Source: GitHub Actions.**

### 6. Run it
**Actions → "Update trending content & publish" → Run workflow.** About 2 minutes later your site is live at `site_url`. After that it runs on its own every 6 hours. To change how often, edit the `cron` line in `.github/workflows/publish.yml`.

---

## How it behaves
- **No duplicate coverage.** A topic covered in the last `skip_recently_covered_days` days is skipped.
- **Sensitive topics stay clean.** Deaths, tragedies, crime, disasters and partisan politics get an article but **no affiliate links**. Categories in `no_monetize_categories` are never monetized either.
- **News section.** Shows headlines and sources only, linking out to the original publisher. Nothing is republished.
- **No API key?** The site still updates, but each post is a short roundup of headlines and is marked `noindex` so thin pages don't hurt you in Google.
- **Your IDs live in one place.** Links are built at render time, so changing your Amazon tag or ClickBank nickname updates every page on the next build.
- **Editing.** All content lives in `data/posts.json`. Edit or delete an entry there and push, and the site re-renders.

## Running it on your own computer (optional)
```bash
python -m generator.build --offline --no-ai    # test with sample feeds in fixtures/
python -m generator.build                       # live run (set ANTHROPIC_API_KEY first)
python -m http.server -d site 8000              # preview at http://localhost:8000
```
For local preview, temporarily set `site_url` to `http://localhost:8000` so the links resolve.

## Rules worth knowing
- **Amazon Associates:** keep the disclosure in the footer and on each post (already built in). Don't add hard-coded prices, because Amazon only allows prices pulled live from its API. You need 3 qualifying sales within 180 days of signing up or the account closes, so drive some traffic early.
- **ClickBank:** check each vendor's affiliate rules. Some ban certain claims or traffic sources.
- **Google and AI content:** Google penalizes large volumes of low-value auto-generated pages. Keep `posts_per_run` modest, read what goes out, and improve or delete weak posts. A few great articles beat a lot of filler.
- **FTC:** the affiliate disclosure must appear before the links. The post template already does this.

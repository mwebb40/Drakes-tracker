# Drake's Tracker

A daily-refreshing dashboard tracking new Drake's listings on **Vinted**,
**eBay** and **Marrkt**, plus new arrivals and sale price-drops on Drake's
own site and UK stockists (END., Mr Porter, House of Huntington, All Blues
Co — edit `config.py` to add more).

It runs for free on GitHub Actions every morning and publishes a static
page via GitHub Pages — no server to maintain.

## How it works

- **Retailers on Shopify** (Drake's, Marrkt, House of Huntington): pulls the
  store's public `/products.json` feed. This is a real, intentional Shopify
  feature — reliable and not really "scraping" in the fragile sense.
- **Retailers not on Shopify** (END., Mr Porter, All Blues Co): best-effort
  HTML scrape. These will need occasional fixing when the sites redesign —
  see "Extending / fixing scrapers" below.
- **eBay**: official Browse API. Needs your own free developer credentials
  (5 minutes to set up, see below).
- **Vinted**: no official API exists. This uses Vinted's own internal
  search endpoint, which sits behind Datadome anti-bot protection — see
  the "Vinted reliability" section below for what to do if it starts
  getting blocked.

Each run compares the day's results against `data/state.json` (committed
back to the repo) so the dashboard can show what's genuinely new since
yesterday, not just everything currently listed.

## Setup

1. **Create a GitHub repo** and push this folder to it.
2. **Enable GitHub Pages**: repo Settings → Pages → Source: "Deploy from a
   branch" → Branch: `main` → folder: `/docs`. Your dashboard will be live
   at `https://<you>.github.io/<repo>/` within a minute or two of the first
   run.
3. **eBay API credentials** (free):
   - Sign up at https://developer.ebay.com → "Get an App ID"
   - Create a Production keyset — you'll get a **Client ID** and **Client
     Secret**.
   - In your GitHub repo: Settings → Secrets and variables → Actions → New
     repository secret. Add `EBAY_CLIENT_ID` and `EBAY_CLIENT_SECRET`.
4. That's it — the workflow in `.github/workflows/daily.yml` runs every
   morning at 06:00 UTC (07:00 UK winter time). You can also trigger a run
   manually from the repo's **Actions** tab any time ("Run workflow").

## Running locally (to test before relying on the daily job)

```bash
pip install -r requirements.txt
export EBAY_CLIENT_ID=xxx
export EBAY_CLIENT_SECRET=xxx
python main.py
open docs/index.html   # or just double-click it
```

## Search terms

Vinted and eBay are matched by keyword search rather than a curated brand
page, so what you search for matters. Both take a **list** of terms in
`config.py` — each one is searched separately and results are merged
together with duplicates removed (the same item can genuinely match more
than one term):

```python
VINTED = {
    ...
    "search_terms": ["Drake's", "Drakes London"],
}

EBAY = {
    ...
    "search_terms": ["Drake's London", "Drakes tie", "Drakes London scarf"],
}
```

Add as many as you like — e.g. split out `"Drakes cardigan"` or
`"Drakes waistcoat"` if you want to catch listings where sellers dropped
the brand name from the title but kept a specific item type. Each extra
term is one more request per run, so there's no real ceiling, just
diminishing returns once you're covering the obvious variants.

The retailer stockists (Drake's, Marrkt, END., etc.) work differently: each
one is a fixed collection/brand page on that store's own site rather than a
keyword search, so there's no term list to edit for them — see the
"Adding more stockists" section below instead.

## Filtering by size

Edit `TARGET_SIZES` in `config.py` with your sizes (e.g. `["M", "L", "16"]`
for tops, collar size, whatever mix you wear). Two things happen with this:

- Items in your sizes get a small "Your size" badge.
- The dashboard itself has a **size filter bar** at the top — clickable
  chips built from whatever sizes are in that day's results — so you can
  narrow down to just "M" or just "16" on the page directly, no rerun
  needed. Ties, scarves and pocket squares (no sizing) always show, since
  there's nothing to filter on.

Note: eBay and the HTML-scraped stockists (END., Mr Porter, All Blues Co)
can't reliably surface size from their listing summaries, so those items
always show regardless of filter — check the size on the actual listing
page for those ones.

## Adding more stockists

Edit `config.py`. For any Shopify store, find their Drake's collection URL
(usually `store.com/collections/drakes` or similar) and add:

```python
{"name": "New Store", "platform": "shopify", "base_url": "https://store.com", "collection": "drakes"},
```

For non-Shopify stores, add a `platform: "html"` entry with a `search_url`
pointing at their Drake's/brand page — expect to need to tune
`sources/html_store.py` for that specific site's markup.

## Vinted reliability

The direct API approach (`sources/vinted.py`) is free and works a lot of
the time, but Vinted's Datadome protection can start blocking requests from
GitHub Actions' shared IP ranges (this is more likely than if you ran it
from your own home connection). If your daily runs start showing zero
Vinted results:

- **Cheapest fix**: run just the Vinted part locally on your own machine
  occasionally and merge results in, or self-host the Action runner.
- **More robust fix**: swap `sources/vinted.py` for a paid scraper service
  (e.g. an Apify Vinted actor, a few dollars per 1,000 results) which
  handles proxy rotation and anti-bot for you. The rest of the pipeline
  (dashboard, state diffing) doesn't need to change — just make `fetch()`
  return the same item shape.

## Limitations / honesty check

- HTML-scraped retailers (END., Mr Porter, All Blues Co) can't reliably
  tell "new" from "not new" or extract price on first pass — treat those
  sections as a starting point to refine, not turnkey.
- This is unofficial use of Vinted's internal API and lightweight scraping
  of retailer HTML — reasonable for a personal low-frequency tracker, but
  worth knowing it sits outside what these sites formally support.

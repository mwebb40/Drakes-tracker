# Drake's Tracker

An hourly-refreshing dashboard tracking new listings across multiple
brands (currently Drake's and RRL — edit `config.py`'s `BRANDS` list to
add more) on **Vinted** and **eBay**, plus new arrivals and sale
price-drops on each brand's own retail stockists where configured (right
now that's Drake's own site, Marrkt, House of Huntington, END., Mr Porter
and All Blues Co).

It runs for free on GitHub Actions and publishes a static page via GitHub
Pages — no server to maintain.

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

Each run compares its results against `data/state.json` (committed back to
the repo), which records when each listing was first seen - not just
whether it's been seen before - so the dashboard can show what's
genuinely new (today, this week) rather than everything currently listed.

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
4. That's it — the workflow in `.github/workflows/daily.yml` runs once an
   hour, at :13 past (deliberately not on the exact hour - GitHub's own
   scheduler is most likely to delay or silently skip runs set for the top
   of the hour, since that's when every other repo's hourly cron also
   fires). You can also trigger a run manually from the repo's **Actions**
   tab any time ("Run workflow"). If Vinted results start disappearing (see
   "Vinted reliability" below), drop the cron back to something sparser,
   e.g. `"13 */4 * * *"` for every 4 hours.

## Running locally (to test before relying on the scheduled job)

```bash
pip install -r requirements.txt
export EBAY_CLIENT_ID=xxx
export EBAY_CLIENT_SECRET=xxx
python main.py
open docs/index.html   # or just double-click it
```

## Adding a brand

`config.py`'s `BRANDS` is a list — each entry is one brand's full setup
(retail stockists, Vinted brand ID(s), eBay search terms). Add a brand by
adding an entry with the same shape as the existing ones (Drake's, RRL);
no other code changes needed. Every item picks up a `brand` field from
whichever `BRANDS` entry produced it, and the dashboard gets a **"Filter
by brand"** chip row automatically whenever more than one brand's items
are present in a run — everything else (sections, size/source/recency
filters, sold-out, wishlist, "My sizes") works the same across brands.

## Search terms

Each brand's `ebay` config takes a **list** of search terms — each one is
searched separately and results are merged together with duplicates
removed (the same item can genuinely match more than one term):

```python
"ebay": {
    "enabled": True,
    "search_terms": ["Drake's London", "Drakes tie", "Drakes London scarf"],
    "category_id": None,
},
```

Add as many as you like — e.g. split out `"Drakes cardigan"` or
`"Drakes waistcoat"` if you want to catch listings where sellers dropped
the brand name from the title but kept a specific item type. Each extra
term is one more request per run, so there's no real ceiling, just
diminishing returns once you're covering the obvious variants.

Vinted works differently: it's filtered by each brand's `vinted.brand_ids`
— Vinted's own internal numeric brand ID(s) — instead of keyword search:
narrower and more complete than matching on title text, since it doesn't
depend on the brand name appearing in the listing title, and it doesn't
pick up unrelated noise that just happens to contain the same word (e.g.
"Drake" the rapper, Drake Waterfowl outdoor gear, when searching for
Drake's). Find a brand's ID from its own page URL on Vinted, e.g.
`vinted.co.uk/brand/389025-drakes` → `389025`:

```python
"vinted": {
    "enabled": True,
    "brand_ids": [389025],
    "search_terms": [""],  # fallback only, used if brand_ids is empty/unset
},
```

`brand_ids` is treated as the sole filter whenever it's non-empty —
`search_terms` is only consulted as a fallback if you clear `brand_ids`
entirely. This still relies on an unofficial, undocumented Vinted query
parameter (`brand_ids[]` on their catalog search endpoint) that this
project has gotten wrong once already — an earlier version tried to
resolve a brand *name* to an ID via a guessed lookup endpoint and matched
the wrong brand in production. Hardcoding the ID straight from the brand's
own page URL, as above, avoids that specific failure mode.

Each brand's retail stockists work differently again: each one is a fixed
collection/brand page on that store's own site rather than a keyword
search, so there's no term list to edit for them — see "Adding more
stockists" below instead.

## Filtering by how new something is

The **"Filter by new"** chips (All / New today / New this week) at the top
of the page filter by when an item's listing was first seen by the
tracker, based on the per-item timestamp in `data/state.json` -
independent of which section (New today / On sale / Everything else) it's
displayed under, and combinable with every other filter. "New this week"
includes today's items too (it's cumulative, not a separate 7-day band).
An item only counts as new once - if it's been sitting in `state.json`
since a previous run, filtering to "New today" won't surface it again just
because you're looking at it today.

## Filtering by size

Edit `TARGET_SIZES` in `config.py` with your sizes (e.g. `["M", "L", "16"]`
for tops, collar size, whatever mix you wear). Two things happen with this:

- Items in your sizes get a small "Your size" badge.
- The dashboard itself has a **size filter** — clickable chips built from
  whatever sizes are in that day's results — so you can narrow down to
  just "M" or just "16" on the page directly, no rerun needed. Ties,
  scarves and pocket squares (no sizing) always show, since there's
  nothing to filter on. It's tucked behind a "Filter by size ▾" toggle
  rather than shown by default, since the full chip list can run to 80+
  sizes across all the sources.

Note: eBay and the HTML-scraped stockists (END., Mr Porter, All Blues Co)
can't reliably surface size from their listing summaries. Those items are
marked "Size unknown" on the card and show under "All sizes", but get
filtered out like anything else once you pick a specific size — check the
size on the actual listing page for those ones if you want them included.
A Shopify product that's sold out in every size (common on House of
Huntington's past-season stock) is marked "Sold out" instead — same
filtering behaviour, just a more specific reason.

`TARGET_SIZES` only takes effect on the next run and needs a code change,
though — for something adjustable without touching `config.py`, there's
also **"My sizes"** (linked from the header): a page listing every size
actually seen from sellers in the latest run (not a fixed list), which you
tick to build your own set, saved in your browser (`localStorage`, so it's
per-browser, not synced across devices). The **"My sizes only"** toggle on
the main page then filters to exactly that set with one click, same
filtering behaviour as picking those sizes by hand in the size filter.
Before you've visited "My sizes" for the first time, the toggle falls back
to whatever's in `TARGET_SIZES`.

## Filtering out sold-out items

Whenever a run turns up at least one Shopify product with zero available
variants, a **"Hide sold out"** toggle appears in its own row above the
listings. Only Shopify stores can tell us stock status for certain, so the
toggle only ever hides items it's actually sure are sold out — Vinted,
eBay and the HTML-scraped stockists are unaffected by it either way.

## Wishlist

Every card has a "☆ Save" button, and a **"☆ My wishlist"** link in the
header opens `wishlist.html` — a separate page listing everything you've
saved, with a remove button per item and a "Clear all". This is purely
client-side: saved items live in your browser's `localStorage`, keyed by
each listing's own id, so they survive every hourly regeneration without
needing a server or database. That also means it's per-browser, not
synced across devices, and clearing your browser's site data clears it
too.

## Adding more stockists

Edit `config.py` — add to the `"retailers"` list under the relevant brand
in `BRANDS`. For any Shopify store, find their collection URL for that
brand (usually `store.com/collections/<brand>` or similar) and add:

```python
{"name": "New Store", "platform": "shopify", "base_url": "https://store.com", "collection": "drakes"},
```

For non-Shopify stores, add a `platform: "html"` entry with a `search_url`
pointing at their brand page for that brand — expect to need to tune
`sources/html_store.py` for that specific site's markup. RRL currently
tracks Marrkt (`collections/rrl`); add further stockists there the same
way as you identify them.

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

"""
Runs every source, works out what's genuinely new since the last run (by
diffing against data/state.json, committed back to the repo each time by
the GitHub Action), and writes docs/index.html — a static dashboard you can
serve for free with GitHub Pages.

Usage: python main.py
"""
from __future__ import annotations
import html
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone

import config
from sources import shopify_store, html_store, vinted, ebay

STATE_PATH = Path("data/state.json")
DASHBOARD_PATH = Path("docs/index.html")
WISHLIST_PATH = Path("docs/wishlist.html")

BASE_CSS = """
  :root { color-scheme: light; }
  * { box-sizing: border-box; }
  body {
    font-family: 'EB Garamond', Georgia, serif;
    max-width: 900px; margin: 0 auto; padding: 48px 20px 80px;
    background: #f7f4ec; color: #2b2a25;
  }
  .masthead { text-align: center; margin-bottom: 40px; }
  .masthead h1 {
    font-family: 'Cormorant Garamond', Georgia, serif; font-weight: 500;
    font-size: 2.1rem; letter-spacing: 0.03em; margin: 0; text-transform: uppercase;
  }
  .rule-thin { width: 42px; height: 1px; background: #8a7a53; margin: 14px auto; }
  .meta { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.14em; color: #8a8574; }
  .nav-link { color: #7a3b30; text-decoration: none; }
  .nav-link:hover { text-decoration: underline; }

  .section-label {
    font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.16em;
    color: #5c5645; margin: 0 0 18px;
  }
  .section-label.muted { color: #a39c85; }
  .empty { font-style: italic; color: #a39c85; font-size: 0.95rem; margin: 0 0 24px; }
  .rule { height: 1px; background: #ddd6c2; margin: 8px 0 40px; }

  .grid {
    display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
    column-gap: 20px; row-gap: 32px; margin-bottom: 8px;
  }
  .card { position: relative; }
  .card-link { display: block; text-decoration: none; color: inherit; }
  .thumb {
    aspect-ratio: 4/5; background: #eae5d6 center/cover no-repeat;
    display: flex; align-items: center; justify-content: center;
    margin-bottom: 10px; color: #a39c85; font-size: 26px; overflow: hidden;
  }
  .source { font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.1em; color: #8a8574; }
  .title { font-size: 0.95rem; margin: 4px 0 3px; line-height: 1.35; }
  .price { font-size: 0.85rem; color: #5c5645; }
  .price .was { color: #a39c85; text-decoration: line-through; margin-right: 8px; }
  .price .now { color: #7a3b30; }
  .size { font-size: 0.72rem; color: #a39c85; margin-top: 2px; }
  .size.unknown { font-style: italic; }
  .badge {
    display: inline-block; margin-left: 6px; padding: 1px 6px; border-radius: 2px;
    background: #eae5d6; color: #5c5645; font-size: 0.58rem; letter-spacing: 0.06em;
    text-transform: uppercase; vertical-align: 1px;
  }
  .save-btn, .remove-btn {
    position: absolute; top: 6px; right: 6px; z-index: 1;
    width: 28px; height: 28px; border-radius: 50%; border: 1px solid #ddd6c2;
    background: rgba(247,244,236,0.92); color: #a39c85; font-size: 15px; line-height: 1;
    cursor: pointer; display: flex; align-items: center; justify-content: center;
    font-family: inherit; padding: 0;
  }
  .save-btn.saved { color: #7a3b30; border-color: #7a3b30; }
  .remove-btn { color: #7a3b30; }
  .filter-bars { margin-bottom: 36px; }
  .filters { text-align: center; margin-bottom: 14px; }
  .filters:last-child { margin-bottom: 0; }
  .filters-label { font-size: 0.66rem; text-transform: uppercase; letter-spacing: 0.12em; color: #a39c85; margin-bottom: 10px; }
  .filters-collapsible summary {
    font-size: 0.66rem; text-transform: uppercase; letter-spacing: 0.12em; color: #a39c85;
    cursor: pointer; list-style: none; display: inline-block; margin-bottom: 10px;
  }
  .filters-collapsible summary::-webkit-details-marker { display: none; }
  .filters-collapsible summary::after { content: ' ▾'; }
  .filters-collapsible[open] summary::after { content: ' ▴'; }
  .filters-collapsible .filters-body { margin-top: 2px; }
  .chip {
    display: inline-block; padding: 5px 14px; margin: 3px; border: 1px solid #ddd6c2;
    border-radius: 999px; font-size: 0.78rem; color: #5c5645; cursor: pointer;
    background: transparent; font-family: inherit;
  }
  .chip.active { background: #2b2a25; border-color: #2b2a25; color: #f7f4ec; }
  .card.hidden { display: none; }
"""

WISHLIST_JS_HELPERS = """
    var WISHLIST_KEY = 'drakes-wishlist-v1';
    function loadWishlist() {
      try { return JSON.parse(localStorage.getItem(WISHLIST_KEY) || '{}'); }
      catch (e) { return {}; }
    }
    function saveWishlist(map) {
      try { localStorage.setItem(WISHLIST_KEY, JSON.stringify(map)); }
      catch (e) {}
    }
"""


def load_first_seen() -> dict[str, str]:
    """Maps item id -> ISO timestamp of when it was first seen, so the
    dashboard can tell "seen an hour ago" from "seen five days ago" - not
    just whether an id has ever been seen at all."""
    if not STATE_PATH.exists():
        return {}
    try:
        data = json.loads(STATE_PATH.read_text())
    except json.JSONDecodeError:
        return {}
    seen = data.get("seen")
    if isinstance(seen, dict):
        return seen
    # Old state format: a flat list of ids with no per-item timestamp.
    # Best available guess for when they were first seen is this old
    # state's own last_run - not exact, but far better than treating
    # everything already-tracked as brand new just because the state
    # format changed.
    old_ids = data.get("seen_ids") or []
    fallback_ts = data.get("last_run") or datetime.now(timezone.utc).isoformat()
    return {i: fallback_ts for i in old_ids}


def save_state(all_items: list[dict], first_seen: dict[str, str]) -> None:
    now = datetime.now(timezone.utc).isoformat()
    seen = {i["id"]: first_seen.get(i["id"], now) for i in all_items}
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps({
        "last_run": now,
        "seen": seen,
    }, indent=2))


def collect_retailer_items() -> list[dict]:
    items = []
    for store in config.RETAILERS:
        try:
            if store["platform"] == "shopify":
                raw = shopify_store.fetch_collection(store["base_url"], store["collection"])
                items.extend(shopify_store.normalize(
                    store["name"], store["base_url"], raw, config.LOOKBACK_DAYS, config.TARGET_SIZES))
            elif store["platform"] == "html":
                items.extend(html_store.fetch(store["name"], store["search_url"]))
        except Exception as e:
            print(f"[main] {store['name']} failed: {e}")
    return items


def collect_resale_items() -> list[dict]:
    items = []
    if config.VINTED.get("enabled"):
        items.extend(vinted.fetch(
            config.VINTED["domain"], config.VINTED["search_terms"], config.TARGET_SIZES,
            brand_ids=config.VINTED.get("brand_ids"),
        ))
    if config.EBAY.get("enabled"):
        items.extend(ebay.fetch(
            config.EBAY["search_terms"], config.EBAY["site"], config.EBAY["category_id"],
            config.EBAY["client_id_env"], config.EBAY["client_secret_env"],
        ))
    return items


def _chip_buttons(group: str, values: list[str], all_label: str) -> str:
    chips = [f'<button class="chip active" data-group="{group}" data-value="__all__">{html.escape(all_label)}</button>']
    for v in values:
        esc = html.escape(v)
        chips.append(f'<button class="chip" data-group="{group}" data-value="{esc}">{esc}</button>')
    return "".join(chips)


def render_chip_bar(label: str, group: str, values: list[str], all_label: str) -> str:
    if not values:
        return ""
    return (f'<div class="filters"><div class="filters-label">{html.escape(label)}</div>'
            f'{_chip_buttons(group, values, all_label)}</div>')


def render_collapsible_chip_bar(label: str, group: str, values: list[str], all_label: str) -> str:
    """Same as render_chip_bar, but tucked behind a native <details> toggle -
    for chip groups (like sizes) with enough values that showing them all
    the time would dominate the page."""
    if not values:
        return ""
    return (f'<details class="filters filters-collapsible">'
            f'<summary>{html.escape(label)}</summary>'
            f'<div class="filters-body">{_chip_buttons(group, values, all_label)}</div>'
            f'</details>')


def render_sold_out_toggle(any_sold_out: bool) -> str:
    if not any_sold_out:
        return ""
    return ('<div class="filters"><div class="filters-label">Availability</div>'
            '<button class="chip" id="hide-sold-out">Hide sold out</button></div>')


def render_recency_filter() -> str:
    return (
        '<div class="filters"><div class="filters-label">Filter by new</div>'
        '<button class="chip active" data-recency-filter="all">All</button>'
        '<button class="chip" data-recency-filter="today">New today</button>'
        '<button class="chip" data-recency-filter="week">New this week</button>'
        '</div>'
    )


def render_dashboard(items: list[dict], first_seen: dict[str, str]) -> str:
    now = datetime.now(timezone.utc)

    def recency_bucket(i: dict) -> str:
        """"today" (seen within 24h), "week" (within 7 days) or "older" -
        based on when an item's id was first recorded in state.json, not
        the self-reported is_new flag some sources always set to True."""
        ts = first_seen.get(i["id"])
        if ts:
            try:
                age = now - datetime.fromisoformat(ts)
            except ValueError:
                age = timedelta(0)
        else:
            age = timedelta(0)  # never seen before - definitionally brand new
        if age <= timedelta(hours=24):
            return "today"
        if age <= timedelta(days=7):
            return "week"
        return "older"

    new_arrivals = [i for i in items if recency_bucket(i) == "today"]
    on_sale = [i for i in items if i.get("on_sale")]
    everything_else = [i for i in items if i not in new_arrivals and i not in on_sale]

    all_sizes = sorted({s for i in items for s in (i.get("sizes") or [])})
    all_sources = sorted({i["source"] for i in items})
    any_sold_out = any(i.get("sold_out") is True for i in items)

    def card(i: dict) -> str:
        price_html = ""
        if i.get("price") is not None:
            price_html = f"£{i['price']:.0f}"
            if i.get("compare_at_price"):
                price_html = (f'<span class="was">£{i["compare_at_price"]:.0f}</span>'
                               f'<span class="now">£{i["price"]:.0f}</span>')
        img_style = f'style="background-image:url(\'{i["image"]}\')"' if i.get("image") else ""
        icon = "" if i.get("image") else '<i class="ti ti-hanger-2"></i>'
        sizes = i.get("sizes") or []
        sold_out = i.get("sold_out") is True
        # "Unknown" means the source couldn't tell us a size at all (eBay,
        # HTML-scraped retailers, a sold-out Shopify product) - distinct from
        # a genuinely one-size item (ties, scarves) where size_match is True
        # with no sizes to list.
        size_unknown = not sizes and i.get("size_match") is None
        if sizes:
            size_bit = f'<div class="size">{" · ".join(sizes)}</div>'
        elif sold_out:
            size_bit = '<div class="size unknown">Sold out</div>'
        elif size_unknown:
            size_bit = '<div class="size unknown">Size unknown</div>'
        else:
            size_bit = ""
        badge = '<span class="badge">Your size</span>' if i.get("size_match") and sizes else ""
        data_sizes = html.escape(json.dumps(sizes))
        data_source = html.escape(i['source'])
        data_unknown = "1" if size_unknown else "0"
        data_sold_out = "1" if sold_out else "0"
        data_recency = recency_bucket(i)
        wish_id = html.escape(i['id'])
        wish_title = html.escape(i['title'] or 'Untitled')
        wish_url = html.escape(i['url'])
        wish_image = html.escape(i['image']) if i.get('image') else ''
        wish_price = i['price'] if i.get('price') is not None else ''
        wish_compare = i['compare_at_price'] if i.get('compare_at_price') else ''
        return f"""
        <div class="card" data-sizes="{data_sizes}" data-source="{data_source}" data-unknown="{data_unknown}" data-sold-out="{data_sold_out}" data-recency="{data_recency}">
          <button type="button" class="save-btn" data-id="{wish_id}" data-title="{wish_title}" data-url="{wish_url}" data-image="{wish_image}" data-source="{data_source}" data-price="{wish_price}" data-compare-price="{wish_compare}" aria-label="Save to wishlist">☆</button>
          <a class="card-link" href="{i['url']}" target="_blank" rel="noopener">
            <div class="thumb" {img_style}>{icon}</div>
            <div class="source">{i['source']}{badge}</div>
            <div class="title">{i['title'] or 'Untitled'}</div>
            <div class="price">{price_html}</div>
            {size_bit}
          </a>
        </div>"""

    def section(title: str, items_: list[dict], muted: bool = False) -> str:
        cls = "section-label muted" if muted else "section-label"
        if not items_:
            return f'<div class="{cls}">{title}</div><p class="empty">Nothing here right now.</p><div class="rule"></div>'
        return (f'<div class="{cls}">{title}</div>'
                f'<div class="grid">{"".join(card(i) for i in items_)}</div>'
                f'<div class="rule"></div>')

    generated = datetime.now(timezone.utc).strftime("%-d %B %Y, %H:%M UTC")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Drake's Tracker</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;500&family=EB+Garamond:ital@0;1&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/tabler-icons/2.44.0/iconfont/tabler-icons.min.css">
<style>
{BASE_CSS}
</style>
</head>
<body>
  <div class="masthead">
    <h1>Drake's Tracker</h1>
    <div class="rule-thin"></div>
    <div class="meta">Updated {generated} · {len(items)} pieces across Vinted, eBay, Marrkt &amp; UK stockists</div>
    <div class="meta" style="margin-top:6px;"><a class="nav-link" href="wishlist.html">☆ My wishlist</a></div>
  </div>
  <div class="filter-bars">
    {render_recency_filter()}
    {render_chip_bar("Filter by source", "source", all_sources, "All sources")}
    {render_collapsible_chip_bar("Filter by size", "size", all_sizes, "All sizes")}
    {render_sold_out_toggle(any_sold_out)}
  </div>
  {section("New today", new_arrivals)}
  {section("On sale", on_sale)}
  {section("Everything else", everything_else, muted=True)}
  <script>
    (function() {{
      var state = {{size: new Set(), source: new Set(), recency: 'all'}};
      var hideSoldOut = false;
      var chips = document.querySelectorAll('.chip[data-group]');
      var cards = document.querySelectorAll('.card');
      function apply() {{
        cards.forEach(function(c) {{
          try {{
            var sizes = [];
            try {{ sizes = JSON.parse(c.dataset.sizes || '[]'); }} catch (e) {{}}
            if (!Array.isArray(sizes)) sizes = [];
            var noSizeInfo = sizes.length === 0;
            var isUnknownSize = c.dataset.unknown === '1';
            var sizeMatch = state.size.size === 0 || (noSizeInfo && !isUnknownSize) ||
              sizes.some(function(s) {{ return state.size.has(s); }});
            var sourceMatch = state.source.size === 0 || state.source.has(c.dataset.source || '');
            var soldOutOk = !(hideSoldOut && c.dataset.soldOut === '1');
            var recencyMatch = state.recency === 'all' ||
              (state.recency === 'today' && c.dataset.recency === 'today') ||
              (state.recency === 'week' && c.dataset.recency !== 'older');
            c.classList.toggle('hidden', !(sizeMatch && sourceMatch && soldOutOk && recencyMatch));
          }} catch (e) {{
            console.error('[filter] failed for card', c, e);
          }}
        }});
      }}
      var soldOutToggle = document.getElementById('hide-sold-out');
      if (soldOutToggle) {{
        soldOutToggle.addEventListener('click', function() {{
          hideSoldOut = !hideSoldOut;
          soldOutToggle.classList.toggle('active', hideSoldOut);
          apply();
        }});
      }}
      var recencyChips = document.querySelectorAll('.chip[data-recency-filter]');
      recencyChips.forEach(function(chip) {{
        chip.addEventListener('click', function() {{
          state.recency = chip.dataset.recencyFilter;
          recencyChips.forEach(function(c) {{ c.classList.remove('active'); }});
          chip.classList.add('active');
          apply();
        }});
      }});
      chips.forEach(function(chip) {{
        chip.addEventListener('click', function() {{
          var group = chip.dataset.group;
          var value = chip.dataset.value;
          var groupChips = document.querySelectorAll('.chip[data-group="' + group + '"]');
          if (value === '__all__') {{
            state[group].clear();
            groupChips.forEach(function(c) {{ c.classList.remove('active'); }});
            chip.classList.add('active');
          }} else {{
            groupChips[0].classList.remove('active');
            if (state[group].has(value)) {{ state[group].delete(value); chip.classList.remove('active'); }}
            else {{ state[group].add(value); chip.classList.add('active'); }}
          }}
          apply();
        }});
      }});
    }})();
  </script>
  <script>
    {WISHLIST_JS_HELPERS}
    (function() {{
      var wishlist = loadWishlist();
      var saveButtons = document.querySelectorAll('.save-btn');
      function refreshButton(btn) {{
        var isSaved = !!wishlist[btn.dataset.id];
        btn.classList.toggle('saved', isSaved);
        btn.textContent = isSaved ? '★' : '☆';
        btn.setAttribute('aria-label', isSaved ? 'Remove from wishlist' : 'Save to wishlist');
      }}
      saveButtons.forEach(function(btn) {{
        refreshButton(btn);
        btn.addEventListener('click', function(e) {{
          e.preventDefault();
          e.stopPropagation();
          var id = btn.dataset.id;
          if (wishlist[id]) {{
            delete wishlist[id];
          }} else {{
            wishlist[id] = {{
              title: btn.dataset.title,
              url: btn.dataset.url,
              image: btn.dataset.image,
              source: btn.dataset.source,
              price: btn.dataset.price ? parseFloat(btn.dataset.price) : null,
              comparePrice: btn.dataset.comparePrice ? parseFloat(btn.dataset.comparePrice) : null,
              savedAt: new Date().toISOString()
            }};
          }}
          saveWishlist(wishlist);
          refreshButton(btn);
        }});
      }});
    }})();
  </script>
</body>
</html>"""


def render_wishlist_page() -> str:
    """Static shell - all the actual content is rendered client-side from
    localStorage, since there's no server/database here to persist a
    per-visitor wishlist. Regenerated each run purely to stay in sync with
    the dashboard's styling/scripts; its own markup never changes."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>My Wishlist — Drake's Tracker</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;500&family=EB+Garamond:ital@0;1&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/tabler-icons/2.44.0/iconfont/tabler-icons.min.css">
<style>
{BASE_CSS}
</style>
</head>
<body>
  <div class="masthead">
    <h1>My Wishlist</h1>
    <div class="rule-thin"></div>
    <div class="meta"><a class="nav-link" href="index.html">← Back to tracker</a></div>
  </div>
  <div id="wishlist-actions" style="text-align:center; margin-bottom:24px; display:none;">
    <button type="button" class="chip" id="clear-wishlist">Clear all</button>
  </div>
  <p id="wishlist-empty" class="empty" style="text-align:center; display:none;">Nothing saved yet — star an item on the tracker to add it here.</p>
  <div id="wishlist-grid" class="grid"></div>
  <script>
    {WISHLIST_JS_HELPERS}
    (function() {{
      var wishlist = loadWishlist();
      var grid = document.getElementById('wishlist-grid');
      var emptyMsg = document.getElementById('wishlist-empty');
      var actions = document.getElementById('wishlist-actions');

      function buildCard(id, item) {{
        var card = document.createElement('div');
        card.className = 'card';

        var removeBtn = document.createElement('button');
        removeBtn.type = 'button';
        removeBtn.className = 'remove-btn';
        removeBtn.setAttribute('aria-label', 'Remove from wishlist');
        removeBtn.textContent = '✕';
        removeBtn.addEventListener('click', function(e) {{
          e.preventDefault();
          e.stopPropagation();
          delete wishlist[id];
          saveWishlist(wishlist);
          render();
        }});

        var link = document.createElement('a');
        link.className = 'card-link';
        link.href = item.url || '#';
        link.target = '_blank';
        link.rel = 'noopener';

        var thumb = document.createElement('div');
        thumb.className = 'thumb';
        if (item.image) {{
          var img = document.createElement('img');
          img.src = item.image;
          img.alt = '';
          img.style.width = '100%';
          img.style.height = '100%';
          img.style.objectFit = 'cover';
          thumb.appendChild(img);
        }} else {{
          thumb.innerHTML = '<i class="ti ti-hanger-2"></i>';
        }}

        var source = document.createElement('div');
        source.className = 'source';
        source.textContent = item.source || '';

        var title = document.createElement('div');
        title.className = 'title';
        title.textContent = item.title || 'Untitled';

        var price = document.createElement('div');
        price.className = 'price';
        if (item.price) {{
          var text = '£' + Math.round(item.price);
          if (item.comparePrice) {{ text = '£' + Math.round(item.comparePrice) + ' → ' + text; }}
          price.textContent = text;
        }}

        link.appendChild(thumb);
        link.appendChild(source);
        link.appendChild(title);
        link.appendChild(price);
        card.appendChild(removeBtn);
        card.appendChild(link);
        return card;
      }}

      function render() {{
        var ids = Object.keys(wishlist).sort(function(a, b) {{
          return (wishlist[b].savedAt || '').localeCompare(wishlist[a].savedAt || '');
        }});
        grid.innerHTML = '';
        if (ids.length === 0) {{
          emptyMsg.style.display = 'block';
          actions.style.display = 'none';
          return;
        }}
        emptyMsg.style.display = 'none';
        actions.style.display = 'block';
        ids.forEach(function(id) {{ grid.appendChild(buildCard(id, wishlist[id])); }});
      }}

      document.getElementById('clear-wishlist').addEventListener('click', function() {{
        if (!confirm('Remove all saved items?')) return;
        wishlist = {{}};
        saveWishlist(wishlist);
        render();
      }});

      render();
    }})();
  </script>
</body>
</html>"""


def main() -> None:
    first_seen = load_first_seen()

    retailer_items = collect_retailer_items()
    resale_items = collect_resale_items()
    all_items = retailer_items + resale_items

    DASHBOARD_PATH.parent.mkdir(parents=True, exist_ok=True)
    DASHBOARD_PATH.write_text(render_dashboard(all_items, first_seen))
    WISHLIST_PATH.write_text(render_wishlist_page())

    save_state(all_items, first_seen)
    print(f"Done. {len(all_items)} items total, dashboard written to {DASHBOARD_PATH}")


if __name__ == "__main__":
    main()

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
from datetime import datetime, timezone

import config
from sources import shopify_store, html_store, vinted, ebay

STATE_PATH = Path("data/state.json")
DASHBOARD_PATH = Path("docs/index.html")


def load_previous_ids() -> set[str]:
    if STATE_PATH.exists():
        try:
            return set(json.loads(STATE_PATH.read_text()).get("seen_ids", []))
        except json.JSONDecodeError:
            return set()
    return set()


def save_state(all_items: list[dict]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps({
        "last_run": datetime.now(timezone.utc).isoformat(),
        "seen_ids": [i["id"] for i in all_items],
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
        items.extend(vinted.fetch(config.VINTED["domain"], config.VINTED["search_terms"], config.TARGET_SIZES))
    if config.EBAY.get("enabled"):
        items.extend(ebay.fetch(
            config.EBAY["search_terms"], config.EBAY["site"], config.EBAY["category_id"],
            config.EBAY["client_id_env"], config.EBAY["client_secret_env"],
        ))
    return items


def render_chip_bar(label: str, group: str, values: list[str], all_label: str) -> str:
    if not values:
        return ""
    chips = [f'<button class="chip active" data-group="{group}" data-value="__all__">{html.escape(all_label)}</button>']
    for v in values:
        esc = html.escape(v)
        chips.append(f'<button class="chip" data-group="{group}" data-value="{esc}">{esc}</button>')
    return f'<div class="filters"><div class="filters-label">{html.escape(label)}</div>{"".join(chips)}</div>'


def render_dashboard(items: list[dict], previously_seen: set[str]) -> str:
    new_arrivals = [i for i in items if i["id"] not in previously_seen or i.get("is_new")]
    on_sale = [i for i in items if i.get("on_sale")]
    everything_else = [i for i in items if i not in new_arrivals and i not in on_sale]

    all_sizes = sorted({s for i in items for s in (i.get("sizes") or [])})
    all_sources = sorted({i["source"] for i in items})

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
        size_bit = f'<div class="size">{" · ".join(sizes)}</div>' if sizes else ""
        badge = '<span class="badge">Your size</span>' if i.get("size_match") and sizes else ""
        data_sizes = html.escape(json.dumps(sizes))
        data_source = html.escape(i['source'])
        return f"""
        <a class="card" href="{i['url']}" target="_blank" rel="noopener" data-sizes="{data_sizes}" data-source="{data_source}">
          <div class="thumb" {img_style}>{icon}</div>
          <div class="source">{i['source']}{badge}</div>
          <div class="title">{i['title'] or 'Untitled'}</div>
          <div class="price">{price_html}</div>
          {size_bit}
        </a>"""

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
  :root {{ color-scheme: light; }}
  * {{ box-sizing: border-box; }}
  body {{
    font-family: 'EB Garamond', Georgia, serif;
    max-width: 900px; margin: 0 auto; padding: 48px 20px 80px;
    background: #f7f4ec; color: #2b2a25;
  }}
  .masthead {{ text-align: center; margin-bottom: 40px; }}
  .masthead h1 {{
    font-family: 'Cormorant Garamond', Georgia, serif; font-weight: 500;
    font-size: 2.1rem; letter-spacing: 0.03em; margin: 0; text-transform: uppercase;
  }}
  .rule-thin {{ width: 42px; height: 1px; background: #8a7a53; margin: 14px auto; }}
  .meta {{ font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.14em; color: #8a8574; }}

  .section-label {{
    font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.16em;
    color: #5c5645; margin: 0 0 18px;
  }}
  .section-label.muted {{ color: #a39c85; }}
  .empty {{ font-style: italic; color: #a39c85; font-size: 0.95rem; margin: 0 0 24px; }}
  .rule {{ height: 1px; background: #ddd6c2; margin: 8px 0 40px; }}

  .grid {{
    display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
    column-gap: 20px; row-gap: 32px; margin-bottom: 8px;
  }}
  .card {{ display: block; text-decoration: none; color: inherit; }}
  .thumb {{
    aspect-ratio: 4/5; background: #eae5d6 center/cover no-repeat;
    display: flex; align-items: center; justify-content: center;
    margin-bottom: 10px; color: #a39c85; font-size: 26px;
  }}
  .source {{ font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.1em; color: #8a8574; }}
  .title {{ font-size: 0.95rem; margin: 4px 0 3px; line-height: 1.35; }}
  .price {{ font-size: 0.85rem; color: #5c5645; }}
  .price .was {{ color: #a39c85; text-decoration: line-through; margin-right: 8px; }}
  .price .now {{ color: #7a3b30; }}
  .size {{ font-size: 0.72rem; color: #a39c85; margin-top: 2px; }}
  .badge {{
    display: inline-block; margin-left: 6px; padding: 1px 6px; border-radius: 2px;
    background: #eae5d6; color: #5c5645; font-size: 0.58rem; letter-spacing: 0.06em;
    text-transform: uppercase; vertical-align: 1px;
  }}
  .filters {{ text-align: center; margin-bottom: 14px; }}
  .filters:last-of-type {{ margin-bottom: 36px; }}
  .filters-label {{ font-size: 0.66rem; text-transform: uppercase; letter-spacing: 0.12em; color: #a39c85; margin-bottom: 10px; }}
  .chip {{
    display: inline-block; padding: 5px 14px; margin: 3px; border: 1px solid #ddd6c2;
    border-radius: 999px; font-size: 0.78rem; color: #5c5645; cursor: pointer;
    background: transparent; font-family: inherit;
  }}
  .chip.active {{ background: #2b2a25; border-color: #2b2a25; color: #f7f4ec; }}
  .card.hidden {{ display: none; }}
</style>
</head>
<body>
  <div class="masthead">
    <h1>Drake's Tracker</h1>
    <div class="rule-thin"></div>
    <div class="meta">Updated {generated} · {len(items)} pieces across Vinted, eBay, Marrkt &amp; UK stockists</div>
  </div>
  {render_chip_bar("Filter by size", "size", all_sizes, "All sizes")}
  {render_chip_bar("Filter by source", "source", all_sources, "All sources")}
  {section("New today", new_arrivals)}
  {section("On sale", on_sale)}
  {section("Everything else", everything_else, muted=True)}
  <script>
    (function() {{
      var state = {{size: new Set(), source: new Set()}};
      var chips = document.querySelectorAll('.chip');
      var cards = document.querySelectorAll('.card');
      function apply() {{
        cards.forEach(function(c) {{
          var sizes = [];
          try {{ sizes = JSON.parse(c.dataset.sizes || '[]'); }} catch (e) {{}}
          var noSizeInfo = sizes.length === 0;
          var sizeMatch = state.size.size === 0 || noSizeInfo ||
            sizes.some(function(s) {{ return state.size.has(s); }});
          var sourceMatch = state.source.size === 0 || state.source.has(c.dataset.source || '');
          c.classList.toggle('hidden', !(sizeMatch && sourceMatch));
        }});
      }}
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
</body>
</html>"""


def main() -> None:
    previously_seen = load_previous_ids()

    retailer_items = collect_retailer_items()
    resale_items = collect_resale_items()
    all_items = retailer_items + resale_items

    DASHBOARD_PATH.parent.mkdir(parents=True, exist_ok=True)
    DASHBOARD_PATH.write_text(render_dashboard(all_items, previously_seen))

    save_state(all_items)
    print(f"Done. {len(all_items)} items total, dashboard written to {DASHBOARD_PATH}")


if __name__ == "__main__":
    main()

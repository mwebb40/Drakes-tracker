"""
Best-effort fallback for retailers that aren't on Shopify (END., Mr Porter,
etc). These sites render listings via JavaScript in the browser, so a plain
requests+BeautifulSoup fetch often only sees a skeleton page — this module
grabs whatever product links/titles it can find in the raw HTML.

This is the most fragile part of the whole project: selectors WILL break
when these sites redesign. Treat entries from "html" sources as a bonus,
not a guarantee, and check the README for how to swap in a headless-browser
(Playwright) version if you want this to be more reliable.
"""
from __future__ import annotations
import re
import requests
from datetime import datetime, timezone
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; DrakesTracker/1.0)"}


def fetch(store_name: str, search_url: str) -> list[dict]:
    try:
        resp = requests.get(search_url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[html_store] {store_name}: failed to fetch ({e})")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    items = []
    seen_urls = set()

    # Generic heuristic: any <a> whose href looks like a product page and
    # whose visible text is non-trivial. Good enough as a starting point —
    # customize per-site in this function if you want tighter matches.
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(strip=True)
        if not text or len(text) < 4:
            continue
        if not re.search(r"/(product|products|item|p)/", href):
            continue
        url = href if href.startswith("http") else requests.compat.urljoin(search_url, href)
        if url in seen_urls:
            continue
        seen_urls.add(url)
        items.append({
            "source": store_name,
            "type": "retailer",
            "title": text,
            "url": url,
            "price": None,
            "compare_at_price": None,
            "on_sale": None,  # unknown — HTML fallback doesn't reliably extract price
            "is_new": None,   # unknown — no reliable date signal without state tracking
            "sizes": [],      # unknown — no reliable size signal without per-site tuning
            "size_match": None,
            "image": None,
            "id": f"{store_name}:{url}",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        })
    return items

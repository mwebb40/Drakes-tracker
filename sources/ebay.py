"""
eBay's official Browse API requires developer program approval, which isn't
guaranteed (rejections happen with no route to appeal). This instead scrapes
eBay's own public search results page - no account, no API key, same
lightweight-HTML approach already used for non-Shopify retailers in
html_store.py. It's unofficial and the page markup can change without
notice, but eBay's search results are plain server-rendered HTML (not a
JS app), so a plain requests+BeautifulSoup fetch reliably sees real results,
unlike the JS-heavy retailer sites html_store.py has to guess at.

eBay's edge does block requests that don't look like a real browser (a bare
"python-requests" User-Agent gets an immediate 403, including from GitHub
Actions' shared IP ranges) - a full browser-style header set plus a cookie
warm-up against the homepage first (same trick sources/vinted.py uses
against Vinted's Datadome) is enough to pass.
"""
from __future__ import annotations
import re
import time
import requests
from datetime import datetime, timezone
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}

# Maps the eBay "marketplace ID" style site codes already used elsewhere in
# this project's config (config.EBAY_SITE) to eBay's own search domain.
SITE_DOMAINS = {
    "EBAY-GB": "www.ebay.co.uk",
    "EBAY-US": "www.ebay.com",
    "EBAY-DE": "www.ebay.de",
    "EBAY-AU": "www.ebay.com.au",
}

_PRICE_RE = re.compile(r"[\d,]+\.\d{2}|\d+")
_ITEM_ID_RE = re.compile(r"/itm/(?:[^/]+/)?(\d+)")


def _parse_price(text: str) -> float | None:
    if not text:
        return None
    match = _PRICE_RE.search(text.replace(",", ""))
    return float(match.group()) if match else None


def _search_one(session: requests.Session, domain: str, keywords: str,
                 category_id: str | None, limit: int) -> list[dict]:
    params = {"_nkw": keywords, "_sop": "10"}  # _sop=10: newly listed first
    if category_id:
        params["_sacat"] = category_id

    resp = session.get(f"https://{domain}/sch/i.html", params=params, timeout=20)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    items = []
    for card in soup.select("li.s-item"):
        link = card.select_one("a.s-item__link")
        title_el = card.select_one(".s-item__title")
        if not link or not link.get("href") or not title_el:
            continue
        title = title_el.get_text(strip=True)
        if not title or title.lower() == "shop on ebay":
            continue  # eBay always injects one non-result placeholder card

        url = link["href"].split("?")[0]
        id_match = _ITEM_ID_RE.search(url)
        item_id = id_match.group(1) if id_match else url

        img = card.select_one(".s-item__image-img")
        image = (img.get("src") or img.get("data-src")) if img else None

        price_el = card.select_one(".s-item__price")
        price = _parse_price(price_el.get_text(strip=True)) if price_el else None

        items.append({
            "source": "eBay",
            "type": "resale",
            "title": title,
            "url": url,
            "price": price,
            "compare_at_price": None,
            "on_sale": None,
            "is_new": True,  # sorted newly-listed first - first_seen tracking still governs actual recency
            # eBay's search results don't reliably expose size (it's buried in
            # per-item "item specifics", a separate page per listing) -
            # unknown sizes always show rather than being filtered out.
            "sizes": [],
            "size_match": None,
            "image": image,
            "id": f"ebay:{item_id}",
            "matched_term": keywords,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        })
        if len(items) >= limit:
            break
    return items


def fetch(keywords: list[str] | str, site: str, category_id: str | None = None,
          limit: int = 60) -> list[dict]:
    """keywords can be a single string or a list - each term gets its own
    search, results are merged and deduplicated by eBay item ID (an item can
    legitimately match more than one of your terms)."""
    if isinstance(keywords, str):
        keywords = [keywords]

    domain = SITE_DOMAINS.get(site)
    if not domain:
        print(f"[ebay] unknown site '{site}' - add it to SITE_DOMAINS in sources/ebay.py")
        return []

    session = requests.Session()
    session.headers.update(HEADERS)
    try:
        # Warm-up: picks up eBay's anon session cookies before hitting search,
        # the same trick sources/vinted.py uses against Vinted's Datadome -
        # a cold request straight to /sch/i.html gets a 403 from eBay's edge.
        session.get(f"https://{domain}/", timeout=20)
    except requests.RequestException as e:
        print(f"[ebay] warm-up failed ({e}) - likely blocked, skipping this run")
        return []

    seen_ids = set()
    items = []
    for term in keywords:
        try:
            batch = _search_one(session, domain, term, category_id, limit)
        except requests.RequestException as e:
            print(f"[ebay] search '{term}' failed ({e})")
            continue
        for it in batch:
            if it["id"] in seen_ids:
                continue
            seen_ids.add(it["id"])
            items.append(it)
        time.sleep(1)  # small gap between searches, politer to eBay's edge
    return items

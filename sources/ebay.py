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
_CURRENCY_PRICE_RE = re.compile(r"[£$€]\s?\d{1,4}(?:,\d{3})*(?:\.\d{2})?")
_ITEM_ID_RE = re.compile(r"/itm/(?:[^/]+/)?(\d+)")

# eBay's own image CDN size convention, visible in any image URL on their
# site (".../s-l140.jpg", ".../s-l500.jpg", etc - "s-l<pixels>"). Search
# results embed a small thumbnail (usually s-l140, sometimes smaller) by
# default even though the same file is served at much larger sizes on the
# listing's own page - swapping the size segment still resolves since it's
# the same underlying image, just a different pre-rendered size.
_EBAY_IMAGE_SIZE_RE = re.compile(r"/s-l\d+(?=\.(?:jpg|jpeg|png|webp)(?:[?#]|$))", re.IGNORECASE)


def _upgrade_image(url: str | None) -> str | None:
    if not url:
        return url
    return _EBAY_IMAGE_SIZE_RE.sub("/s-l500", url)

# Standard clothing letter sizes, always looked for in a title regardless of
# your own TARGET_SIZES - sellers routinely put these in the title itself
# ("Drake's Wool Tie M") even though eBay's search results don't expose a
# proper "item specifics" size field the way a listing's own page does.
_LETTER_SIZES = ["XXXL", "XXL", "XS", "XL", "S", "M", "L"]

# Sellers just as often spell a size out instead of abbreviating it
# ("...Brown Medium" rather than "...Brown M") - mapped to the same letter
# codes so a spelled-out size still matches a letter-based TARGET_SIZES entry.
_WORD_SIZE_MAP = {
    "extra small": "XS",
    "small": "S",
    "medium": "M",
    "large": "L",
    "extra large": "XL",
    "extra extra large": "XXL",
}


def _extract_sizes(title: str, target_sizes: list[str] | None) -> list[str]:
    """Best-effort size extraction from listing titles - the same kind of
    heuristic html_store.py already relies on for JS-heavy retailer sites,
    since eBay's search results (unlike a listing's own page) don't carry a
    structured size field. Checks a fixed vocabulary of letter sizes (as
    both abbreviations and spelled-out words) plus whatever sizes you've
    configured (TARGET_SIZES), so e.g. a collar size like "16" or a shoe
    size only gets matched if it's one you actually asked to track - not
    any bare number in the title (a price fragment, a model year, a
    listing count)."""
    if not title:
        return []
    found = []

    # Word-based matches first, longest phrase first, masking each match out
    # of the working copy as it's found - otherwise "large" (itself a valid
    # standalone match) fires from inside "extra large" before the longer
    # phrase gets a chance, wrongly adding both L and XL for one item.
    working = title
    for phrase, letter in sorted(_WORD_SIZE_MAP.items(), key=lambda kv: len(kv[0]), reverse=True):
        match = re.search(rf"\b{re.escape(phrase)}\b", working, re.IGNORECASE)
        if not match:
            continue
        if letter not in found:
            found.append(letter)
        working = working[:match.start()] + "#" * (match.end() - match.start()) + working[match.end():]

    vocab = sorted(set(_LETTER_SIZES) | set(target_sizes or []), key=len, reverse=True)
    for token in vocab:
        if token in found:
            continue
        # Excluding apostrophes from the boundary matters a lot here -
        # without it, the "s" in a plain possessive like "Drake's" or
        # "Men's" (nearly every title in this project) reads as a
        # standalone size "S".
        pattern = re.compile(rf"(?<![A-Za-z0-9'’]){re.escape(token)}(?![A-Za-z0-9'’])", re.IGNORECASE)
        if pattern.search(working):
            found.append(token)

    return found


def _parse_price(text: str) -> float | None:
    if not text:
        return None
    match = _PRICE_RE.search(text.replace(",", ""))
    return float(match.group()) if match else None


def _find_price_near(anchor) -> float | None:
    """Walk up from a listing's title/link to the enclosing card and pull
    the first price-looking string out of its text - robust to eBay's class
    names changing since it doesn't depend on them at all. Requires a
    currency symbol so it can't grab an unrelated number (an item ID, a
    size, a rating count) the way a bare-digit match could."""
    node = anchor
    for _ in range(6):  # climb a handful of ancestor levels
        node = node.parent
        if node is None:
            break
        match = _CURRENCY_PRICE_RE.search(node.get_text(" ", strip=True))
        if match:
            return _parse_price(match.group(0))
    return None


def _find_image_near(anchor) -> str | None:
    """Same climb as _find_price_near, but for a thumbnail - eBay sometimes
    wraps the image in its own separate <a> next to (not inside) the title
    link, so an image search scoped to the title link alone can miss it."""
    node = anchor
    img = node.find("img")
    for _ in range(6):
        if img is not None:
            break
        node = node.parent
        if node is None:
            break
        img = node.find("img")
    return (img.get("src") or img.get("data-src")) if img else None


def _make_item(url: str, item_id: str, title: str, price: float | None,
               image: str | None, keywords: str, target_sizes: list[str] | None) -> dict:
    sizes = _extract_sizes(title, target_sizes)
    # No size found in the title is genuinely ambiguous - could be a
    # one-size item (a tie, a scarf) or just a seller who left it out of
    # the title - so it stays "unknown" (bypasses the size filter) rather
    # than being treated as a confident non-match, same convention as
    # sources/vinted.py.
    size_match = None if not sizes else any(s in (target_sizes or []) for s in sizes)
    return {
        "source": "eBay",
        "type": "resale",
        "title": title,
        "url": url,
        "price": price,
        "compare_at_price": None,
        "on_sale": None,
        "is_new": True,  # sorted newly-listed first - first_seen tracking still governs actual recency
        "sizes": sizes,
        "size_match": size_match,
        "image": _upgrade_image(image),
        "id": f"ebay:{item_id}",
        "matched_term": keywords,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def _from_item_cards(soup: BeautifulSoup, keywords: str, target_sizes: list[str] | None) -> list[dict]:
    """The classic eBay search result markup (li.s-item, with a fixed set of
    sub-classes for title/price/image). Cheap to check first when it applies,
    but eBay has multiple result-grid layouts in rotation and this one won't
    always be what a given request gets back - see _from_item_links below."""
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

        items.append(_make_item(url, item_id, title, price, image, keywords, target_sizes))
    return items


def _from_item_links(soup: BeautifulSoup, keywords: str, target_sizes: list[str] | None) -> list[dict]:
    """Generic fallback, same technique html_store.py uses for JS-heavy
    retailer sites: find every link that actually points at a listing
    (/itm/<id>) regardless of whatever CSS classes eBay's current experiment
    bucket happens to wrap it in, then pull whatever title/price/image text
    we can find nearby. Less precise than _from_item_cards but far more
    resilient to eBay's markup changing under us."""
    items = []
    seen_ids = set()
    for a in soup.find_all("a", href=True):
        id_match = _ITEM_ID_RE.search(a["href"])
        if not id_match:
            continue
        item_id = id_match.group(1)
        if item_id in seen_ids:
            continue

        title = _CURRENCY_PRICE_RE.sub("", a.get_text(" ", strip=True)).strip()
        if not title:
            img_in_link = a.find("img")
            title = (img_in_link.get("alt") or "").strip() if img_in_link else ""
        if not title or title.lower() == "shop on ebay":
            continue

        seen_ids.add(item_id)
        url = a["href"].split("?")[0]
        price = _find_price_near(a)
        image = _find_image_near(a)

        items.append(_make_item(url, item_id, title, price, image, keywords, target_sizes))
    return items


def _search_one(session: requests.Session, domain: str, keywords: str,
                 category_id: str | None, limit: int, target_sizes: list[str] | None) -> list[dict]:
    params = {
        "_nkw": keywords,
        "_sop": "10",  # newly listed first
        "LH_PrefLoc": "1",  # "Item location" filter, same param eBay's own
                            # search UI sends when you tick "UK Only" (or
                            # whichever country the site domain is for) -
                            # excludes listings shipping from elsewhere.
    }
    if category_id:
        params["_sacat"] = category_id

    resp = session.get(f"https://{domain}/sch/i.html", params=params, timeout=20)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    items = _from_item_cards(soup, keywords, target_sizes)
    if not items:
        items = _from_item_links(soup, keywords, target_sizes)
    if not items:
        # Neither strategy found anything on a 200 response - probably an
        # anti-bot interstitial rather than real results. Logging the page
        # title (not the full body) gives a next-run debugging clue without
        # spamming the log.
        page_title = soup.title.get_text(strip=True) if soup.title else "(no <title>)"
        print(f"[ebay] search '{keywords}' returned 0 results (page title: {page_title!r})")
    return items[:limit]


def fetch(keywords: list[str] | str, site: str, category_id: str | None = None,
          target_sizes: list[str] | None = None, limit: int = 60) -> list[dict]:
    """keywords can be a single string or a list - each term gets its own
    search, results are merged and deduplicated by eBay item ID (an item can
    legitimately match more than one of your terms). target_sizes (e.g.
    config.TARGET_SIZES) is checked against each listing's title alongside a
    fixed set of standard letter sizes - see _extract_sizes()."""
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
            batch = _search_one(session, domain, term, category_id, limit, target_sizes)
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

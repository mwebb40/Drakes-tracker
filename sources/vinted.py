"""
Vinted has no public API. This uses their internal catalog search endpoint
(the same one their own web frontend calls) — reverse-engineered, unofficial,
and sitting behind Datadome anti-bot protection.

Practical notes:
  - A plain, low-frequency (once a day) request from a residential-ish IP
    (e.g. your own machine) tends to work. GitHub Actions' shared IP ranges
    get blocked more often — if that happens to you, see README for the
    Playwright-cookie or Apify-actor fallback.
  - We first hit the homepage to pick up cookies/session before calling the
    API, which helps pass basic bot checks.
"""
from __future__ import annotations
import requests
from datetime import datetime, timezone

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "application/json",
}


import time


def _to_item(it: dict, target_sizes: list[str], matched_term: str) -> dict:
    size = it.get("size_title")  # Vinted's own free-text size field, e.g. "M", "16", "One size"
    sizes = [size] if size else []
    # No size_title at all is ambiguous - could be a seller who left it
    # blank, or a non-clothing hit (a book, poster, record) our keyword
    # search happened to catch - either way it's not safe to assume
    # "fits everyone" the way an explicit "One size" would be.
    size_match = None if not sizes else any(s in target_sizes for s in sizes)
    return {
        "source": "Vinted",
        "type": "resale",
        "title": it.get("title"),
        "url": it.get("url"),
        "price": float(it["price"]["amount"]) if it.get("price") else None,
        "compare_at_price": None,
        "on_sale": None,
        "is_new": True,  # every search hit is "new" in the sense of newly listed
        "sizes": sizes,
        "size_match": size_match,
        "image": (it.get("photo") or {}).get("url"),
        "id": f"vinted:{it.get('id')}",
        "matched_term": matched_term,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def _catalog_search(session: requests.Session, domain: str, params: dict) -> list[dict]:
    resp = session.get(
        f"https://www.{domain}/api/v2/catalog/items",
        params=params,
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json().get("items", [])


def _fetch_by_brand_id(session: requests.Session, domain: str, brand_id: int,
                        target_sizes: list[str], per_page: int) -> list[dict]:
    raw = _catalog_search(session, domain, {
        "brand_ids[]": brand_id,
        "order": "newest_first",
        "per_page": per_page,
    })
    return [_to_item(it, target_sizes, matched_term=f"brand:{brand_id}") for it in raw]


def _fetch_by_keyword(session: requests.Session, domain: str, search_text: str,
                       target_sizes: list[str], per_page: int) -> list[dict]:
    raw = _catalog_search(session, domain, {
        "search_text": search_text,
        "order": "newest_first",
        "per_page": per_page,
    })
    return [_to_item(it, target_sizes, matched_term=search_text) for it in raw]


def fetch(domain: str, search_terms: list[str] | str, target_sizes: list[str] | None = None,
          per_page: int = 60, brand_ids: list[int] | None = None) -> list[dict]:
    """If `brand_ids` is given (Vinted's own internal numeric brand IDs -
    find one from a brand's page URL, e.g. vinted.co.uk/brand/389025-drakes
    -> 389025), filters the catalog directly by brand_ids[] - narrower and
    more complete than keyword search since it doesn't depend on the brand
    name appearing in the listing title, and it's one request per ID
    instead of one per search term. Each ID's results are merged and
    deduplicated by listing ID.

    Falls back to the keyword `search_terms` loop (single string or list,
    each term searched separately and merged/deduplicated) only when
    `brand_ids` is empty/unset - a configured brand_ids list is treated as
    the sole filter, not something to silently fall back away from."""
    target_sizes = target_sizes or []

    session = requests.Session()
    session.headers.update(HEADERS)

    try:
        # Warm up: picks up the anon session cookie Vinted expects on API calls.
        session.get(f"https://www.{domain}/", timeout=20)
    except requests.RequestException as e:
        print(f"[vinted] warm-up failed ({e}) — likely blocked by Datadome. "
              f"See README for fallback options.")
        return []

    seen_ids = set()
    items = []

    if brand_ids:
        for brand_id in brand_ids:
            try:
                batch = _fetch_by_brand_id(session, domain, brand_id, target_sizes, per_page)
            except requests.RequestException as e:
                print(f"[vinted] brand search for id={brand_id} failed ({e}) — "
                      f"likely blocked by Datadome. See README for fallback options.")
                continue
            for it in batch:
                if it["id"] not in seen_ids:
                    seen_ids.add(it["id"])
                    items.append(it)
            time.sleep(1)  # small gap between requests, politer to the anti-bot system
        return items

    if isinstance(search_terms, str):
        search_terms = [search_terms]
    for term in search_terms:
        if not term:
            continue  # skip blank placeholder terms (e.g. when brand_ids is the intended filter)
        try:
            batch = _fetch_by_keyword(session, domain, term, target_sizes, per_page)
        except requests.RequestException as e:
            print(f"[vinted] search '{term}' failed ({e}) — likely blocked by Datadome. "
                  f"See README for fallback options.")
            continue
        for it in batch:
            if it["id"] in seen_ids:
                continue
            seen_ids.add(it["id"])
            items.append(it)
        time.sleep(1)  # small gap between searches, politer to the anti-bot system
    return items

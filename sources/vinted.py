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


def _fetch_one(session: requests.Session, domain: str, search_text: str, target_sizes: list[str],
                per_page: int) -> list[dict]:
    resp = session.get(
        f"https://www.{domain}/api/v2/catalog/items",
        params={
            "search_text": search_text,
            "order": "newest_first",
            "per_page": per_page,
        },
        timeout=20,
    )
    resp.raise_for_status()
    data = resp.json()

    items = []
    for it in data.get("items", []):
        size = it.get("size_title")  # Vinted's own free-text size field, e.g. "M", "16", "One size"
        sizes = [size] if size else []
        size_match = (not sizes) or any(s in target_sizes for s in sizes)
        items.append({
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
            "matched_term": search_text,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        })
    return items


def fetch(domain: str, search_terms: list[str] | str, target_sizes: list[str] | None = None,
          per_page: int = 60) -> list[dict]:
    """search_terms can be a single string or a list — each term gets its own
    search, results are merged and deduplicated by listing ID (the same item
    can legitimately match more than one of your terms, e.g. "Drake's" and
    "Drake's tie")."""
    if isinstance(search_terms, str):
        search_terms = [search_terms]
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
    for term in search_terms:
        try:
            batch = _fetch_one(session, domain, term, target_sizes, per_page)
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

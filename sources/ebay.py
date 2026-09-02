"""
eBay Browse API (official, legitimate, free tier). Requires your own
credentials from https://developer.ebay.com — see README for the 5-minute
signup. This uses the client_credentials OAuth flow (no user login needed,
just an App ID + Cert ID).
"""
from __future__ import annotations
import os
import base64
import requests
from datetime import datetime, timezone

TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"


def _get_token(client_id: str, client_secret: str) -> str | None:
    creds = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    resp = requests.post(
        TOKEN_URL,
        headers={
            "Authorization": f"Basic {creds}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "client_credentials",
            "scope": "https://api.ebay.com/oauth/api_scope",
        },
        timeout=20,
    )
    if resp.status_code != 200:
        print(f"[ebay] token request failed: {resp.status_code} {resp.text[:200]}")
        return None
    return resp.json().get("access_token")


def _search_one(keywords: str, site: str, category_id: str | None, token: str, limit: int) -> list[dict]:
    params = {
        "q": keywords,
        "sort": "newlyListed",
        "limit": limit,
    }
    if category_id:
        params["category_ids"] = category_id

    resp = requests.get(
        SEARCH_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "X-EBAY-C-MARKETPLACE-ID": site,
        },
        params=params,
        timeout=20,
    )
    if resp.status_code != 200:
        print(f"[ebay] search '{keywords}' failed: {resp.status_code} {resp.text[:200]}")
        return []

    data = resp.json()
    items = []
    for it in data.get("itemSummaries", []):
        price = it.get("price", {})
        items.append({
            "source": "eBay",
            "type": "resale",
            "title": it.get("title"),
            "url": it.get("itemWebUrl"),
            "price": float(price["value"]) if price.get("value") else None,
            "compare_at_price": None,
            "on_sale": None,
            "is_new": True,  # newlyListed sort — every result is a fresh listing
            # eBay's search results don't reliably expose size (it's buried in
            # per-item "item specifics", a separate API call per listing) —
            # unknown sizes always show rather than being filtered out.
            "sizes": [],
            "size_match": None,
            "image": (it.get("image") or {}).get("imageUrl"),
            "id": f"ebay:{it.get('itemId')}",
            "matched_term": keywords,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        })
    return items


def fetch(keywords: list[str] | str, site: str, category_id: str | None,
          client_id_env: str, client_secret_env: str, limit: int = 50) -> list[dict]:
    """keywords can be a single string or a list — each term gets its own
    search, results are merged and deduplicated by eBay item ID (an item can
    legitimately match more than one of your terms)."""
    if isinstance(keywords, str):
        keywords = [keywords]

    client_id = os.environ.get(client_id_env)
    client_secret = os.environ.get(client_secret_env)
    if not client_id or not client_secret:
        print(f"[ebay] skipped — set {client_id_env} and {client_secret_env} "
              f"as environment variables / GitHub Actions secrets.")
        return []

    token = _get_token(client_id, client_secret)
    if not token:
        return []

    seen_ids = set()
    items = []
    for term in keywords:
        for it in _search_one(term, site, category_id, token, limit):
            if it["id"] in seen_ids:
                continue
            seen_ids.add(it["id"])
            items.append(it)
    return items

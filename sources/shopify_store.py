"""
Generic fetcher for any Shopify store. Uses the public, unauthenticated
/products.json storefront endpoint that every Shopify store exposes — this
is a documented, intentional Shopify feature (not a scraping workaround),
so it's far more reliable than parsing HTML.

Detects:
  - new arrivals: products whose `published_at` is within LOOKBACK_DAYS,
    or that weren't present in our saved state from the previous run.
  - sale items: any variant where compare_at_price > price.
"""
from __future__ import annotations
import time
import requests
from datetime import datetime, timezone, timedelta

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; DrakesTracker/1.0)"}


def _get_json(url: str, params: dict | None = None) -> dict:
    resp = requests.get(url, params=params, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.json()


def fetch_collection(base_url: str, collection_handle: str, per_page: int = 250) -> list[dict]:
    """Pull every product in a Shopify collection via /collections/<handle>/products.json."""
    products = []
    page = 1
    while True:
        url = f"{base_url.rstrip('/')}/collections/{collection_handle}/products.json"
        data = _get_json(url, params={"limit": per_page, "page": page})
        batch = data.get("products", [])
        if not batch:
            break
        products.extend(batch)
        if len(batch) < per_page:
            break
        page += 1
        time.sleep(0.5)  # be polite
    return products


def fetch_all_products_filtered_by_vendor(base_url: str, vendor_name: str, per_page: int = 250) -> list[dict]:
    """Fallback for stores with no dedicated collection: pull /products.json and filter client-side."""
    products = []
    page = 1
    vendor_lower = vendor_name.lower()
    while True:
        url = f"{base_url.rstrip('/')}/products.json"
        data = _get_json(url, params={"limit": per_page, "page": page})
        batch = data.get("products", [])
        if not batch:
            break
        products.extend([p for p in batch if vendor_lower in (p.get("vendor") or "").lower()])
        if len(batch) < per_page:
            break
        page += 1
        time.sleep(0.5)
    return products


def _extract_sizes(product: dict) -> tuple[list[str], bool]:
    """Pull the available (in-stock) size values from a Shopify product's variants.

    Shopify stores size under whichever option is literally named "Size"
    (case-insensitive); falls back to the variant title if there's no
    matching option, which covers most single-option stores too.

    Returns (sizes, has_size_option). has_size_option tells the caller
    whether this product has a real size dimension at all (a jumper, say)
    as opposed to genuinely being one-size (a tie) - a product can have a
    size option and still come back with an empty sizes list if every size
    is currently sold out, which is a different situation from "no sizing
    applies here" and needs to be flagged differently on the dashboard.
    """
    options = product.get("options", [])
    size_option_index = None
    for idx, opt in enumerate(options):
        if isinstance(opt, dict) and (opt.get("name") or "").strip().lower() == "size":
            size_option_index = idx
            break
        if isinstance(opt, str) and opt.strip().lower() == "size":
            size_option_index = idx
            break

    sizes = []
    for v in product.get("variants", []):
        if not v.get("available"):
            continue
        if size_option_index is not None:
            val = v.get(f"option{size_option_index + 1}")
        else:
            val = v.get("option1") or v.get("title")
        if val and val.lower() != "default title" and val not in sizes:
            sizes.append(val)
    return sizes, size_option_index is not None


def normalize(store_name: str, base_url: str, raw_products: list[dict], lookback_days: int,
              target_sizes: list[str] | None = None) -> list[dict]:
    """Turn raw Shopify product JSON into our common item format."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    target_sizes = target_sizes or []
    items = []
    for p in raw_products:
        variants = p.get("variants", [])
        prices = [float(v["price"]) for v in variants if v.get("price")]
        compare_prices = [float(v["compare_at_price"]) for v in variants if v.get("compare_at_price")]
        min_price = min(prices) if prices else None
        max_compare = max(compare_prices) if compare_prices else None
        on_sale = bool(max_compare and min_price and max_compare > min_price)

        sizes, has_size_option = _extract_sizes(p)
        if sizes:
            size_match = any(s in target_sizes for s in sizes)
        elif has_size_option:
            # Has a real size dimension but nothing currently in stock -
            # unknown which size(s) it'll come back in, not "fits everyone".
            size_match = None
        else:
            # No size option at all (ties, scarves, pocket squares) counts as
            # always matching — there's nothing to filter on.
            size_match = True

        published_at = p.get("published_at") or p.get("created_at")
        is_new = False
        if published_at:
            try:
                pub_dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
                is_new = pub_dt >= cutoff
            except ValueError:
                pass

        image = None
        if p.get("images"):
            image = p["images"][0].get("src")

        items.append({
            "source": store_name,
            "type": "retailer",
            "title": p.get("title"),
            "url": f"{base_url.rstrip('/')}/products/{p.get('handle')}",
            "price": min_price,
            "compare_at_price": max_compare,
            "on_sale": on_sale,
            "is_new": is_new,
            "sizes": sizes,
            "size_match": size_match,
            "image": image,
            "id": f"{store_name}:{p.get('id')}",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        })
    return items

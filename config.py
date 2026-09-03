"""
Central config for the Drake's tracker.
Add/remove stockists here — no other code changes needed for Shopify-based sites.
"""

BRAND_NAME = "Drake's"

# How many days back counts as "new" when a store doesn't give us a
# proper diff to work from (first run, or a store without stable dates).
LOOKBACK_DAYS = 2

# ---------------------------------------------------------------------------
# 1. RETAIL STOCKISTS (sell NEW stock; we track new arrivals + sale price drops)
#
# `collection` is the store's Shopify collection handle for Drake's, i.e. the
# bit in the URL: https://shop.com/collections/<handle>
# If a store doesn't have a dedicated Drake's collection, use vendor_filter
# instead, which pulls /products.json and filters by vendor name client-side
# (slower, works on any Shopify store regardless of collection setup).
#
# platform: "shopify" (uses the public /products.json trick) or "html"
# (generic keyword scrape of a search/sale page — more fragile, best-effort).
# ---------------------------------------------------------------------------
RETAILERS = [
    {
        "name": "Drake's (official)",
        "platform": "shopify",
        "base_url": "https://uk.drakes.com",
        "collection": "clothing",  # adjust/add more collections if needed
    },
    {
        "name": "Marrkt (pre-owned, but also lists rare new-old-stock)",
        "platform": "shopify",
        "base_url": "https://www.marrkt.com",
        "collection": "drakes",
    },
    {
        "name": "House of Huntington (past-season outlet)",
        "platform": "shopify",
        "base_url": "https://houseofhuntington.com",
        "collection": "drakes-london-menswear",
    },
    {
        "name": "END.",
        "platform": "html",
        "search_url": "https://www.endclothing.com/gb/brands/drake-s",
    },
    {
        "name": "Mr Porter",
        "platform": "html",
        "search_url": "https://www.mrporter.com/en-gb/mens/designer/drakes",
    },
    {
        "name": "All Blues Co",
        "platform": "html",
        "search_url": "https://allbluescostore.com/product-tag/drakes-menswear-and-accessories/",
    },
    # Add more UK stockists here, e.g. Trunk Clothiers, Oi Polloi, The Bureau Belfast:
    # {"name": "Trunk Clothiers", "platform": "html", "search_url": "https://www.trunkclothiers.com/..."},
]

# ---------------------------------------------------------------------------
# 2. SECONDHAND / RESALE MARKETPLACES
# ---------------------------------------------------------------------------

VINTED = {
    "enabled": True,
    "domain": "vinted.co.uk",
    # Vinted's own internal numeric brand ID(s) for Drake's - found from the
    # brand's actual page URL: vinted.co.uk/brand/389025-drakes -> 389025.
    # Filtering by brand_ids[] instead of keyword search cuts out noise from
    # unrelated listings that just contain the word "Drake"/"Drake's" (Drake
    # the rapper, Drake Waterfowl outdoor gear, etc. - see git history for
    # what that noise looked like). Treated as the sole filter whenever it's
    # non-empty; `search_terms` below is only used as a fallback if this is
    # empty/unset. An earlier attempt at this resolved a brand *name* to an
    # ID via a guessed lookup endpoint and got it wrong in production
    # (matched "adidas") - this ID was found directly from Vinted's own
    # brand page instead, not guessed, but the brand_ids[] catalog filter
    # itself is still unverified against a live response from here, so
    # check the first run's Vinted results look right before trusting it.
    "brand_ids": [389025],
    # Fallback: used only if `brand_ids` above is empty/unset. One or more
    # search terms, each searched separately with results merged/deduplicated.
    "search_terms": [""],
    # Vinted sits behind Datadome anti-bot protection. The direct endpoint
    # below works without login for casual/low-frequency use but can start
    # returning 401/403 if it decides your traffic looks automated. See
    "notes": "See README for fallback options if this starts failing.",
}

EBAY = {
    "enabled": True,
    "site": "EBAY-GB",
    # One or more search terms — each is searched separately and results are
    # merged/deduplicated.
    "search_terms": ["Drake's London", "Drakes tie", "Drakes London scarf"],
    # Category 57988 = Men's Ties; leave as None to search all categories.
    "category_id": None,
    # Requires your own free eBay Developer account (see README).
    "client_id_env": "EBAY_CLIENT_ID",
    "client_secret_env": "EBAY_CLIENT_SECRET",
}

MARRKT_URL = "https://www.marrkt.com/collections/drakes"

# ---------------------------------------------------------------------------
# 3. YOUR SIZES
#
# Items matching one of these get a "your size" flag on the dashboard.
# This does NOT hide other sizes — everything still shows, with a filter
# bar on the page itself so you can toggle sizes on/off there without
# needing to edit this file or rerun anything. Use whatever labels the
# sites themselves use, e.g.:
#   Clothing:  "S", "M", "L", "XL"
#   Shirts:    "15", "15.5", "16"  (collar size)
#   Shoes:     "8", "9", "9.5"     (UK sizing)
#   Ties/scarves/pocket squares are one-size, so they always match.
# ---------------------------------------------------------------------------
TARGET_SIZES = ["M", "L", "16"]


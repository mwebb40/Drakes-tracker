"""
Central config for the tracker - a list of BRANDS, each with its own
retail stockists, Vinted brand ID(s), and eBay search terms. Add a new
brand by adding an entry to BRANDS; no other code changes needed for
Shopify-based retailers or for Vinted/eBay coverage.
"""

# How many days back counts as "new" when a store doesn't give us a
# proper diff to work from (first run, or a store without stable dates).
LOOKBACK_DAYS = 2

# Shared across all brands: Vinted has one search domain, and one eBay
# developer app covers searches for every brand.
VINTED_DOMAIN = "vinted.co.uk"
EBAY_SITE = "EBAY-GB"
EBAY_CLIENT_ID_ENV = "EBAY_CLIENT_ID"
EBAY_CLIENT_SECRET_ENV = "EBAY_CLIENT_SECRET"

# ---------------------------------------------------------------------------
# BRANDS
#
# Each entry:
#   "name"      - shown on the dashboard (source labels, the brand filter).
#   "retailers" - stockists selling NEW stock; we track new arrivals + sale
#                 price drops. `collection` is the store's Shopify collection
#                 handle for this brand, i.e. the bit in the URL:
#                 https://shop.com/collections/<handle>. platform: "shopify"
#                 (public /products.json feed) or "html" (generic keyword
#                 scrape of a search/sale page - more fragile, best-effort).
#   "vinted"    - brand_ids (Vinted's own internal numeric brand ID(s), found
#                 from the brand's page URL, e.g. vinted.co.uk/brand/389025-
#                 drakes -> 389025) filters the catalog directly - narrower
#                 and more complete than keyword search, and doesn't depend
#                 on the brand name appearing in the listing title. Treated
#                 as the sole filter whenever non-empty; search_terms is
#                 only used as a fallback if brand_ids is empty/unset.
#   "ebay"      - one or more search terms, each searched separately with
#                 results merged/deduplicated. category_id: leave None to
#                 search all categories.
# ---------------------------------------------------------------------------
BRANDS = [
    {
        "name": "Drake's",
        "retailers": [
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
            {
                "name": "Son of a Stag",
                "platform": "shopify",
                "base_url": "https://sonofastag.com",
                "collection": "drakes",
            },
            # Add more UK stockists here, e.g. Trunk Clothiers, Oi Polloi, The Bureau Belfast:
            # {"name": "Trunk Clothiers", "platform": "html", "search_url": "https://www.trunkclothiers.com/..."},
        ],
        "vinted": {
            "enabled": True,
            "brand_ids": [389025],  # vinted.co.uk/brand/389025-drakes
            "search_terms": [""],  # fallback only, used if brand_ids is empty/unset
        },
        "ebay": {
            "enabled": True,
            "search_terms": ["Drake's London", "Drakes tie", "Drakes London scarf"],
            "category_id": None,
        },
    },
    {
        "name": "RRL",
        "retailers": [
            {
                "name": "Marrkt (pre-owned, but also lists rare new-old-stock)",
                "platform": "shopify",
                "base_url": "https://www.marrkt.com",
                "collection": "rrl",
            },
            {
                "name": "Stuarts London",
                "platform": "shopify",
                "base_url": "https://www.stuartslondon.com",
                "collection": "rrl-by-ralph-lauren",
            },
            {
                "name": "The Sporting Lodge",
                "platform": "shopify",
                "base_url": "https://www.thesportinglodge.com",
                "collection": "rrl-by-ralph-lauren",
            },
            {
                "name": "Son of a Stag",
                "platform": "shopify",
                "base_url": "https://sonofastag.com",
                "collection": "rrl",
            },
            {
                "name": "Yards Store",
                "platform": "shopify",
                "base_url": "https://www.yardsstore.com",
                "collection": "rrl-by-ralph-lauren",
            },
            # Add more stockists here as you identify them.
        ],
        "vinted": {
            "enabled": True,
            "brand_ids": [5179168],  # vinted.co.uk/brand/5179168 - "Double RL by Ralph Lauren"
            "search_terms": ["RRL", "Double RL", "RRL Ralph Lauren"],
        },
        "ebay": {
            "enabled": True,
            "search_terms": ["RRL Ralph Lauren", "Double RL", "RRL denim"],
            "category_id": None,
        },
    },
]

# ---------------------------------------------------------------------------
# YOUR SIZES
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

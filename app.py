"""
app.py

Flask application for the viper.in-style storefront.

Data flow:
    products.json (raw, team-edited)
        -> scripts/clean_products.py  (run manually after edits)
        -> products_clean.json        (loaded here, once, at startup)

This file NEVER reads products.json directly and NEVER writes to either
JSON file at runtime. The product catalog is treated as read-only data
for the lifetime of the running process. If you edit products.json, you
must re-run scripts/clean_products.py and restart/redeploy the app to
pick up the changes — there is no hot-reload of product data by design
(keeps the request path simple and avoids file-lock issues on free-tier
hosting).
"""

import json
import logging
import os
from pathlib import Path

from flask import Flask, abort, jsonify, render_template, request, url_for

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
PRODUCTS_FILE = BASE_DIR / "products_clean.json"

# Fixed category list — same source of truth as scripts/clean_products.py.
# Deliberately not derived from the data, so "Home Appliances" can exist
# as a real, linkable category page with zero products right now.
CATEGORIES = {
    "health_supplements": "Health Supplements",
    "skin_care_products": "Skin Care",
    "grocery": "Groceries",
    "agricultural_products": "Agri Products",
    "home_appliances": "Home Appliances",
}

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 60  # hard ceiling so ?per_page=99999 can't force-load everything

# image_path values in products_clean.json look like "static/images/..."
# but url_for('static', filename=...) already prepends "/static/" itself,
# so this prefix must be stripped before building the URL. Centralizing
# that here (and the empty-path -> placeholder fallback) means templates
# never touch path strings directly.
STATIC_PREFIX = "static/"
PLACEHOLDER_IMAGE_RELATIVE = "images/products/placeholder.svg"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def load_products() -> list[dict]:
    """Load the cleaned product catalog from disk. Called once at startup.

    Raises a clear, loud error at boot if the file is missing or malformed,
    rather than letting the app start in a broken state and fail mysteriously
    on the first request.
    """
    if not PRODUCTS_FILE.exists():
        raise FileNotFoundError(
            f"{PRODUCTS_FILE} not found. Run scripts/clean_products.py first "
            f"to generate it from products.json."
        )

    with open(PRODUCTS_FILE, encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError(f"{PRODUCTS_FILE} should contain a JSON array.")

    unknown = {p["category"] for p in data} - set(CATEGORIES)
    if unknown:
        logger.warning(
            "products_clean.json contains categories not in the known "
            "CATEGORIES list: %s. These products will not be reachable "
            "through any category page.",
            unknown,
        )

    logger.info("Loaded %d products from %s", len(data), PRODUCTS_FILE.name)
    return data


def create_app() -> Flask:
    app = Flask(__name__)

    @app.template_filter("product_image_url")
    def product_image_url(image_path: str) -> str:
        """Convert a stored image_path into a usable /static/... URL,
        falling back to the placeholder when image_path is empty.

        Centralized here so templates never deal with path-prefix
        stripping or the empty-string fallback themselves — they just
        write {{ product.image_path | product_image_url }}.
        """
        if not image_path:
            relative = PLACEHOLDER_IMAGE_RELATIVE
        elif image_path.startswith(STATIC_PREFIX):
            relative = image_path[len(STATIC_PREFIX):]
        else:
            relative = image_path
        return url_for("static", filename=relative)

    @app.template_global("category_display_name")
    def category_display_name(slug: str) -> str:
        """Look up a category's human-readable display name from its
        slug. Used on the product detail page's breadcrumb so it doesn't
        need its own copy of the CATEGORIES dict."""
        return CATEGORIES.get(slug, slug)

    # Loaded once per process. Gunicorn/PythonAnywhere workers each load
    # their own copy in memory — fine at this data size (see earlier sizing
    # discussion: well under a rounding error against free-tier RAM limits).
    products = load_products()
    products_by_id = {p["id"]: p for p in products}

    def serialize_product(product: dict) -> dict:
        """Product dict plus a ready-to-use image_url, for JSON API
        responses. Keeps the same image_path -> URL logic as the
        product_image_url template filter, just reachable from Python."""
        return {**product, "image_url": product_image_url(product["image_path"])}

    # ------------------------------------------------------------------
    # Page routes
    # ------------------------------------------------------------------

    @app.route("/")
    def home():
        # Category cards always render all 5 categories, including any
        # with zero products (e.g. Home Appliances right now) — the
        # template decides how to label an empty category, this route
        # just reports the count.
        category_counts = {slug: 0 for slug in CATEGORIES}
        for p in products:
            if p["category"] in category_counts:
                category_counts[p["category"]] += 1

        categories_for_template = [
            {
                "slug": slug,
                "name": name,
                "count": category_counts[slug],
                "is_empty": category_counts[slug] == 0,
            }
            for slug, name in CATEGORIES.items()
        ]
        return render_template("index.html", categories=categories_for_template)

    @app.route("/category/<slug>")
    def category_page(slug):
        if slug not in CATEGORIES:
            abort(404)

        # Initial server-rendered page shows the first page of results.
        # Further pages are fetched client-side via /api/products as the
        # user scrolls — see script.js. This keeps first paint fast and
        # avoids shipping all 145+ products in the initial HTML.
        page_products = [p for p in products if p["category"] == slug][:DEFAULT_PAGE_SIZE]
        total_count = sum(1 for p in products if p["category"] == slug)

        return render_template(
            "category.html",
            category_slug=slug,
            category_name=CATEGORIES[slug],
            products=page_products,
            total_count=total_count,
            page_size=DEFAULT_PAGE_SIZE,
        )

    @app.route("/product/<int:product_id>")
    def product_page(product_id):
        product = products_by_id.get(product_id)
        if product is None:
            abort(404)
        return render_template("product.html", product=product)

    @app.route("/cart")
    def cart_page():
        # Cart contents live in the browser's localStorage (see script.js),
        # not on the server — there's no logged-in user concept yet, so
        # there's nothing meaningful to render server-side here. The page
        # is a static shell that JS populates on load.
        return render_template("cart.html")

    # ------------------------------------------------------------------
    # JSON API
    # ------------------------------------------------------------------

    @app.route("/api/products")
    def api_products():
        """Paginated product listing, optionally filtered by category.

        Query params:
            category  - a known category slug (optional)
            page      - 1-indexed page number (default 1)
            per_page  - results per page (default 20, max 60)

        Used by the frontend for infinite-scroll / "load more" within a
        category page, and could later back a search results view.
        """
        category = request.args.get("category")
        if category is not None and category not in CATEGORIES:
            return jsonify({"error": f"Unknown category '{category}'"}), 400

        try:
            page = max(1, int(request.args.get("page", 1)))
        except ValueError:
            return jsonify({"error": "page must be an integer"}), 400

        try:
            per_page = int(request.args.get("per_page", DEFAULT_PAGE_SIZE))
        except ValueError:
            return jsonify({"error": "per_page must be an integer"}), 400
        per_page = max(1, min(per_page, MAX_PAGE_SIZE))

        filtered = (
            [p for p in products if p["category"] == category]
            if category
            else products
        )

        start = (page - 1) * per_page
        end = start + per_page
        page_items = [serialize_product(p) for p in filtered[start:end]]

        return jsonify({
            "products": page_items,
            "page": page,
            "per_page": per_page,
            "total_count": len(filtered),
            "has_more": end < len(filtered),
        })

    @app.route("/api/products/<int:product_id>")
    def api_product_detail(product_id):
        """Single product lookup, e.g. for the cart page to display
        current name/price/image for items it only has ids for in
        localStorage."""
        product = products_by_id.get(product_id)
        if product is None:
            return jsonify({"error": "Product not found"}), 404
        return jsonify(serialize_product(product))

    # ------------------------------------------------------------------
    # Error handlers
    # ------------------------------------------------------------------

    @app.errorhandler(404)
    def not_found(e):
        return render_template("404.html"), 404

    @app.errorhandler(500)
    def server_error(e):
        logger.exception("Internal server error")
        return render_template("500.html"), 500

    return app


# Module-level app object — what Gunicorn/Waitress/PythonAnywhere's WSGI
# config will import (e.g. `gunicorn app:app`).
app = create_app()


if __name__ == "__main__":
    # Flask's built-in server — local development only. Never used in
    # production; see deployment notes for Gunicorn/Waitress setup.
    debug_mode = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(debug=debug_mode, host="127.0.0.1", port=5000)
"""
clean_products.py

Reads the raw, hand/team-edited products.json (scraped data, prices as
"₹ N" strings) and produces products_clean.json: the file app.py actually
loads at runtime.

Why this exists as a separate step instead of doing it in app.py:
- The team will keep editing products.json by hand to improve data quality
  (fixing descriptions, adding missing image paths, adding new products).
  Re-running this script after every edit catches mistakes (bad category,
  duplicate id, unparseable price) BEFORE they reach the live app.
- app.py should load clean, typed data (price as int, not "₹ 1,200" string)
  without doing parsing/validation on every server start.

Usage:
    python scripts/clean_products.py
    (run from the project root, or adjust the paths below)

This script is read-only with respect to products.json — it never writes
back to the raw file, only to products_clean.json. Safe to re-run anytime.
"""

import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_PATH = PROJECT_ROOT / "products.json"
CLEAN_PATH = PROJECT_ROOT / "products_clean.json"
IMAGES_DIR = PROJECT_ROOT / "static" / "images" / "products"
PLACEHOLDER_IMAGE = "static/images/products/placeholder.svg"

# The fixed set of categories for the site. This is intentionally NOT
# derived from whatever happens to appear in products.json — it's the
# business's planned category list (including ones with zero products
# right now, like home_appliances), so the UI can always render all five
# tiles and a typo'd category in the data gets caught instead of silently
# creating an orphan 6th category nobody can browse to.
KNOWN_CATEGORIES = {
    "health_supplements": "Health Supplements",
    "skin_care_products": "Skin Care",
    "grocery": "Groceries",
    "agricultural_products": "Agri Products",
    "home_appliances": "Home Appliances",  # no products yet, placeholder tile
}

PRICE_PATTERN = re.compile(r"^₹\s*([\d,]+)$")


def fail(msg: str) -> None:
    print(f"\nERROR: {msg}")
    print("Cleanup aborted — products_clean.json was NOT updated.")
    sys.exit(1)


def main() -> None:
    if not RAW_PATH.exists():
        fail(f"Could not find {RAW_PATH}")

    with open(RAW_PATH, encoding="utf-8") as f:
        raw = json.load(f)

    if not isinstance(raw, list):
        fail("products.json must contain a JSON array at the top level")

    warnings = []   # things we fixed automatically / informational
    problems = []    # things that need a human to edit products.json
    seen_ids = set()
    cleaned = []

    for i, p in enumerate(raw):
        ref = p.get("name", f"index {i}")

        # --- required fields present ---
        for field in ("id", "name", "price", "category", "description", "image_path"):
            if field not in p:
                problems.append(f"'{ref}' is missing required field '{field}'")
        if any(f"missing required field" in msg and ref in msg for msg in problems):
            continue  # can't safely process this entry further

        # --- id: unique, integer ---
        pid = p["id"]
        if not isinstance(pid, int):
            problems.append(f"Product '{ref}' has non-integer id: {pid!r}")
            continue
        if pid in seen_ids:
            problems.append(f"Duplicate id {pid} (product '{ref}')")
            continue
        seen_ids.add(pid)

        # --- category: must be one of the known slugs ---
        category = p["category"]
        if category not in KNOWN_CATEGORIES:
            problems.append(
                f"Product id {pid} ('{ref}') has unknown category '{category}'. "
                f"Expected one of: {', '.join(KNOWN_CATEGORIES)}"
            )
            continue

        # --- price: "₹ N" or "₹ N,NNN" -> int ---
        price_raw = p["price"]
        match = PRICE_PATTERN.match(price_raw.strip())
        if not match:
            problems.append(
                f"Product id {pid} ('{ref}') has unparseable price: {price_raw!r}"
            )
            continue
        price_int = int(match.group(1).replace(",", ""))

        # --- image_path: empty -> placeholder (display-time fallback);
        #     non-empty -> verify the file actually exists on disk ---
        image_path = p["image_path"].strip()
        if image_path == "":
            warnings.append(
                f"Product id {pid} ('{ref}') has no image yet — "
                f"will use placeholder until image_path is filled in."
            )
        else:
            image_file = PROJECT_ROOT / image_path
            if not image_file.exists():
                problems.append(
                    f"Product id {pid} ('{ref}') has image_path "
                    f"'{image_path}' but that file does not exist on disk."
                )
                continue

        # --- description: left untouched per team's request, but flag
        #     suspiciously short ones (likely a future scraper failure,
        #     not something this script tries to fix) ---
        description = p["description"]
        if len(description.strip()) < 30:
            warnings.append(
                f"Product id {pid} ('{ref}') has a very short description "
                f"({len(description.strip())} chars) — worth a manual check."
            )

        cleaned.append({
            "id": pid,
            "name": p["name"].strip(),
            "price": price_int,
            "category": category,
            "description": description,
            "image_path": image_path,  # empty string preserved as-is
        })

    # --- report ---
    print(f"Processed {len(raw)} raw entries -> {len(cleaned)} clean entries.\n")

    if warnings:
        print(f"{len(warnings)} informational warning(s):")
        for w in warnings:
            print(f"  - {w}")
        print()

    if problems:
        print(f"{len(problems)} PROBLEM(S) need manual fixing in products.json:")
        for p_ in problems:
            print(f"  ! {p_}")
        print(
            f"\n{len(cleaned)} of {len(raw)} products were clean and WILL be "
            f"included in products_clean.json. The {len(problems)} flagged "
            f"above were skipped — fix them in products.json and re-run."
        )
    else:
        print("No problems found.")

    # Category coverage summary — useful at a glance after every edit
    print("\nCategory coverage:")
    counts = {slug: 0 for slug in KNOWN_CATEGORIES}
    for p in cleaned:
        counts[p["category"]] += 1
    for slug, display in KNOWN_CATEGORIES.items():
        n = counts[slug]
        note = "  (placeholder — coming soon)" if n == 0 else ""
        print(f"  {display:<20} {n:>4} product(s){note}")

    with open(CLEAN_PATH, "w", encoding="utf-8") as f:
        json.dump(cleaned, f, ensure_ascii=False, indent=2)

    print(f"\nWrote {CLEAN_PATH}")


if __name__ == "__main__":
    main()
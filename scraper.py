"""
Vestige product scraper for vestbuy.in  (v4)

IMAGE DOWNLOAD FIX
------------------
The site blocks direct requests from non-Indian IPs (403).
Solution: use Selenium to navigate to each category/detail page (which works
because Chrome runs locally), then copy the browser's cookies into a
requests.Session. That session looks identical to the browser to the server,
so image downloads succeed.

HOW TO RUN
----------
pip install selenium webdriver-manager requests beautifulsoup4
python scraper.py
"""

import os, re, json, time, random
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager


# ---------------------------------------------------------------------------
# CONFIG  — edit these
# ---------------------------------------------------------------------------

BASE_URL = "https://www.vestbuy.in"

CATEGORIES = [
    {"client_category": "health_supplements",    "url_path": "/Vestige-Products/Vestige-Health-Care-Products"},
    {"client_category": "agricultural_products", "url_path": "/Vestige-Products/Vestige-Agriculture"},
    {"client_category": "grocery",               "url_path": "/Vestige-Products/Vestige-Health-Food"},
    {"client_category": "skin_care_products",    "url_path": "/Vestige-Products/Vestige-Personal-Care-Products"},
]

MAX_PRODUCTS_PER_CATEGORY = None   # was 15, None means no limit
DELAY_RANGE = (1.5, 2.5)           # slightly faster, still polite
HEADLESS     = True

# ---------------------------------------------------------------------------
# PATHS
# ---------------------------------------------------------------------------

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
IMAGE_DIR    = os.path.join(PROJECT_ROOT, "static", "images", "products")
JSON_FILE    = os.path.join(PROJECT_ROOT, "products.json")
os.makedirs(IMAGE_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# ROBOTS.TXT
# ---------------------------------------------------------------------------

_disallowed = None

def _load_robots():
    global _disallowed
    if _disallowed is not None:
        return _disallowed
    _disallowed = []
    try:
        r = requests.get(urljoin(BASE_URL, "/robots.txt"), timeout=10,
                         headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200:
            applies = False
            for line in r.text.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.lower().startswith("user-agent:"):
                    applies = line.split(":", 1)[1].strip() == "*"
                elif applies and line.lower().startswith("disallow:"):
                    p = line.split(":", 1)[1].strip()
                    if p:
                        _disallowed.append(p)
            print(f"  [robots] {len(_disallowed)} disallow rule(s)")
    except Exception as e:
        print(f"  [robots] could not fetch ({e}), proceeding")
    return _disallowed

def can_fetch(url: str) -> bool:
    path = urlparse(url).path
    for d in _load_robots():
        if path.startswith(d):
            return False
    return True


# ---------------------------------------------------------------------------
# SELENIUM SETUP
# ---------------------------------------------------------------------------

def build_driver(headless=True):
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--window-size=1366,900")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
    opts.page_load_strategy = "eager"
    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=opts
    )
    driver.set_page_load_timeout(60)
    return driver


def safe_get(driver, url: str):
    try:
        driver.get(url)
    except TimeoutException:
        print(f"    [warn] page load timeout — continuing with partial DOM")
        try:
            driver.execute_script("window.stop();")
        except Exception:
            pass


def wait_for_products(driver, timeout=30):
    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div.product-block"))
        )
    except TimeoutException:
        pass


def get_soup(driver) -> BeautifulSoup:
    return BeautifulSoup(driver.page_source, "html.parser")


# ---------------------------------------------------------------------------
# REQUESTS SESSION  — synced from Selenium cookies
# ---------------------------------------------------------------------------

def make_session(driver) -> requests.Session:
    """
    Build a requests.Session that mirrors the Selenium browser session.
    The server sees the same cookies → no 403 on image downloads.
    """
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ),
        "Referer": BASE_URL + "/",
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        "Accept-Language": "en-IN,en;q=0.9",
    })
    for cookie in driver.get_cookies():
        session.cookies.set(cookie["name"], cookie["value"],
                            domain=cookie.get("domain", ""),
                            path=cookie.get("path", "/"))
    return session


def download_image(session: requests.Session, url: str, filepath: str) -> bool:
    """Download image using the browser-mirrored session. Returns True on success."""
    if not url:
        return False
    try:
        r = session.get(url, stream=True, timeout=20)
        if r.status_code == 200:
            content_type = r.headers.get("content-type", "")
            if "image" in content_type or "octet" in content_type:
                with open(filepath, "wb") as f:
                    for chunk in r.iter_content(4096):
                        f.write(chunk)
                return True
            else:
                print(f"    [warn] unexpected content-type '{content_type}' for {url}")
        else:
            print(f"    [warn] HTTP {r.status_code} for {url}")
    except Exception as e:
        print(f"    [warn] download error: {e}")
    return False


# ---------------------------------------------------------------------------
# LISTING PAGE PARSER
# ---------------------------------------------------------------------------

def get_total_pages(soup: BeautifulSoup) -> int:
    text = soup.get_text(" ")
    m = re.search(r"\((\d+)\s*Pages?\)", text)
    if m:
        return int(m.group(1))
    pag = soup.find("ul", class_="pagination")
    if pag:
        nums = [int(a.text) for a in pag.find_all("a") if a.text.strip().isdigit()]
        if nums:
            return max(nums)
    return 1


def parse_listing_page(soup: BeautifulSoup) -> list[dict]:
    """
    vestbuy.in card structure (pav_flower theme):
      div.product-block
        div.product-img > a.img[href]  — detail URL / thumbnail
          img[src]                     — thumbnail (relative path)
        div.product-meta
          h5.name > a                  — name
          span.price-new               — current price
          p.description                — short description
        button[onclick="cart.add('ID')] — product_id
    """
    products = []
    for card in soup.find_all("div", class_="product-block"):
        try:
            name_el = card.select_one("h5.name a, h4.name a")
            if not name_el:
                continue
            name       = name_el.get_text(strip=True)
            detail_url = name_el.get("href", "")
            if not name or not detail_url:
                continue
            if not detail_url.startswith("http"):
                detail_url = urljoin(BASE_URL, detail_url)

            pid = None
            btn = card.select_one("button[onclick*='cart.add']")
            if btn:
                m = re.search(r"cart\.add\('(\d+)'\)", btn.get("onclick", ""))
                if m:
                    pid = m.group(1)
            pid = pid or str(abs(hash(detail_url)) % 100000)

            price_el = card.select_one("span.price-new")
            price    = price_el.get_text(strip=True) if price_el else ""

            desc_el = card.select_one("p.description")
            desc    = desc_el.get_text(strip=True) if desc_el else ""

            img_el    = card.select_one("div.product-img img, div.image img")
            thumb_src = img_el.get("src", "") if img_el else ""

            products.append({
                "product_id":  pid,
                "name":        name,
                "price":       price,
                "description": desc,
                "_detail_url": detail_url,
                "_thumb_src":  thumb_src,
            })
        except Exception as e:
            print(f"    [card error] {e}")
    return products


# ---------------------------------------------------------------------------
# DETAIL PAGE ENRICHMENT
# ---------------------------------------------------------------------------

def enrich_product(driver, product: dict) -> str:
    """
    Visit detail page, upgrade description if truncated, return best image URL.
    The thumbnail src on the listing page is e.g. image/cache/catalog/xxx/ID-80x73.jpg
    The detail page anchor href is the larger version e.g. ID-500x457.jpg or ID-300x273.jpg
    We prefer the anchor href (larger), fall back to img src.
    """
    detail_url = product.pop("_detail_url", "")
    if not detail_url or not can_fetch(detail_url):
        return ""

    safe_get(driver, detail_url)
    time.sleep(random.uniform(1.0, 2.0))
    soup = get_soup(driver)

    img_url = ""

    # 1. Anchor href around the main image (points to a larger cached image)
    for sel in ["#product .image a", ".product-image a", ".product-img a.img",
                ".product-img a", "a.product-zoom", ".zoom a"]:
        a = soup.select_one(sel)
        if a:
            href = a.get("href", "")
            if href and any(ext in href.lower() for ext in [".jpg", ".png", ".webp", ".jpeg"]):
                img_url = href
                break

    # 2. img src on the detail page
    if not img_url:
        for sel in ["#product .image img", ".product-image img",
                    "a.thumbnail img", "#content .image img"]:
            el = soup.select_one(sel)
            if el:
                src = el.get("src", "")
                if src and ("catalog" in src or "image" in src):
                    img_url = src
                    break

    # Make absolute
    if img_url and not img_url.startswith("http"):
        img_url = urljoin(BASE_URL, img_url)

    # Fuller description
    if product.get("description", "").endswith("....."):
        for sel in ["#tab-description", ".tab-content #description",
                    "#product-description", ".product-description"]:
            el = soup.select_one(sel)
            if el:
                full = el.get_text(" ", strip=True)
                if len(full) > len(product["description"]):
                    product["description"] = full[:600]
                    break

    return img_url


# ---------------------------------------------------------------------------
# FILENAME HELPER
# ---------------------------------------------------------------------------

def safe_filename(name: str, pid: str, img_url: str) -> str:
    ext  = ".png" if ".png" in img_url.lower() else ".jpg"
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:60]
    return f"{slug}_{pid}{ext}"


# ---------------------------------------------------------------------------
# CATEGORY SCRAPER
# ---------------------------------------------------------------------------

def scrape_category(driver, client_category: str, url_path: str,
                    max_products=None) -> list[dict]:
    first_url = urljoin(BASE_URL, url_path)
    if not can_fetch(first_url):
        print(f"[skip] robots.txt blocks {first_url}")
        return []

    print(f"\n=== Category: {client_category} ===")
    safe_get(driver, first_url)
    time.sleep(random.uniform(*DELAY_RANGE))
    wait_for_products(driver)

    soup        = get_soup(driver)
    total_pages = get_total_pages(soup)
    print(f"  {total_pages} page(s)")

    # ---- Collect product stubs from listing pages ----
    listing_products = []

    for page in range(1, total_pages + 1):
        if max_products and len(listing_products) >= max_products:
            break

        page_url = first_url if page == 1 else f"{first_url}?page={page}"
        if page > 1:
            if not can_fetch(page_url):
                break
            safe_get(driver, page_url)
            time.sleep(random.uniform(*DELAY_RANGE))
            wait_for_products(driver)
            soup = get_soup(driver)

        print(f"  Page {page}/{total_pages}: {page_url}")
        cards = parse_listing_page(soup)
        print(f"    → {len(cards)} products on this page")

        if not cards:
            print("    [warn] no products found")
            continue

        if max_products:
            cards = cards[: max_products - len(listing_products)]

        listing_products.extend(cards)

    print(f"  Collected {len(listing_products)} products; enriching + downloading images...")

    # ---- Enrich each product (visit detail page) ----
    # Build a requests session NOW (after Selenium has visited the site and has cookies)
    session = make_session(driver)

    enriched = []
    for i, p in enumerate(listing_products, 1):
        print(f"  [{i}/{len(listing_products)}] {p['name']}")

        thumb_src = p.pop("_thumb_src", "")
        img_url   = ""

        try:
            img_url = enrich_product(driver, p)
            # Refresh session cookies after each detail page visit
            session = make_session(driver)
        except Exception as e:
            print(f"    [warn] enrichment failed: {e}")
            p.pop("_detail_url", None)

        # Fall back to thumbnail if detail page gave nothing
        if not img_url and thumb_src:
            img_url = urljoin(BASE_URL, thumb_src) if not thumb_src.startswith("http") else thumb_src

        # Download image
        image_path = ""
        if img_url:
            filename = safe_filename(p["name"], p["product_id"], img_url)
            filepath = os.path.join(IMAGE_DIR, filename)
            print(f"    → {img_url[:90]}")
            ok = download_image(session, img_url, filepath)
            if ok:
                image_path = f"static/images/products/{filename}"
                print(f"    ✓ saved {filename}")
            else:
                print(f"    ✗ image download failed")

        p["image_path"] = image_path
        p["category"]   = client_category
        enriched.append(p)

        time.sleep(random.uniform(0.5, 1.0))

    return enriched


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    all_products = []
    driver = build_driver(headless=HEADLESS)

    try:
        # Warm up: visit the homepage so Selenium gets session cookies
        print("Warming up browser session...")
        safe_get(driver, BASE_URL)
        time.sleep(2)

        for cat in CATEGORIES:
            results = scrape_category(
                driver,
                cat["client_category"],
                cat["url_path"],
                max_products=MAX_PRODUCTS_PER_CATEGORY,
            )
            all_products.extend(results)
    finally:
        driver.quit()

    # Renumber IDs sequentially
    final = []
    for i, p in enumerate(all_products, start=1):
        final.append({
            "id":          i,
            "name":        p.get("name", ""),
            "price":       p.get("price", ""),
            "category":    p.get("category", ""),
            "description": p.get("description") or "No description available.",
            "image_path":  p.get("image_path", ""),
        })

    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(final, f, indent=4, ensure_ascii=False)

    saved_images = sum(1 for p in final if p["image_path"])
    print(f"\n✓ Done — {len(final)} products, {saved_images} images saved")
    print(f"  JSON  : {JSON_FILE}")
    print(f"  Images: {IMAGE_DIR}")


if __name__ == "__main__":
    main()
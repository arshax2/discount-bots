"""
migros_bot.py  –  saves discount images to
E:/web/discount-frontend/public/images/migros          (2025-07-25)
"""
import asyncio, json, logging, hashlib, httpx
from pathlib import Path
from playwright.async_api import async_playwright, Page
import os  
# --------------------------------------------------------------------------- #
#  Config & paths
# --------------------------------------------------------------------------- #
OUTPUT_JSON = Path(__file__).resolve().parent.parent / "discounts.json"
IMAGE_DIR   = Path(r"E:/web/discount-frontend/public/images/migros")
IMAGE_DIR.mkdir(parents=True, exist_ok=True)

API_ENDPOINT = os.getenv(
    "DISCOUNTS_API",             # environment variable name
    "http://localhost:10000/api/discounts"   # fallback if the var isn’t set
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
BASE_URL = "https://www.migros.com.tr/tum-indirimli-urunler-dt-0"

def normalize_price(price_str: str) -> float:
    return float(price_str.replace(".", "")
                          .replace(",", ".")
                          .replace("TL", "")
                          .strip())

# --------------------------------------------------------------------------- #
#  Helpers
# --------------------------------------------------------------------------- #
async def scroll_slowly(page: Page) -> None:
    last_h, same = 0, 0
    for _ in range(50):                       # max ~50*0.6 s ≈ 30 s
        await page.mouse.wheel(0, 300)
        await asyncio.sleep(0.6)
        h = await page.evaluate("document.documentElement.scrollHeight")
        if h == last_h:
            same += 1
            if same > 3:
                break
        else:
            same = 0
            last_h = h

async def download_image(url: str, title: str) -> str:
    """
    Downloads an image to IMAGE_DIR and returns **/images/migros/filename**.
    If the URL is invalid or the request fails, returns "" so the caller
    can decide what to do.
    """
    if not url or not url.startswith("http") or "data:image" in url:
        logging.warning(f"⚠️  Skipping invalid image URL: {url}")
        return ""

    # deterministic filename = md5(title+url).ext
    ext = url.split(".")[-1].split("?")[0].lower()
    if len(ext) > 5:                          # junk like "webp?param=x"
        ext = "jpg"
    filename = f"{hashlib.md5((title+url).encode()).hexdigest()}.{ext}"
    filepath = IMAGE_DIR / filename

    # Already on disk?
    if filepath.exists():
        return f"/images/migros/{filename}"

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(url)
            r.raise_for_status()
            filepath.write_bytes(r.content)
            logging.info(f"📥 Saved image → {filepath}")
            return f"/images/migros/{filename}"
    except Exception as e:
        logging.warning(f"❌ Image download failed ({url}): {e}")
        return ""

# --------------------------------------------------------------------------- #
#  Scraper core
# --------------------------------------------------------------------------- #
async def scrape_migros_discounts() -> list[dict]:
    products, page_no = [], 1

    async with async_playwright() as p:
        browser  = await p.chromium.launch(headless=True)
        context  = await browser.new_context()
        page     = await context.new_page()

        while True:
            url = f"{BASE_URL}?sayfa={page_no}"
            logging.info(f"🌐  {url}")
            await page.goto(url, wait_until="domcontentloaded")
            try:
                await page.wait_for_selector("mat-card", timeout=10_000)
            except:
                logging.info("🛑  No product cards found, pagination ends.")
                break

            await scroll_slowly(page)
            cards = await page.query_selector_all("mat-card")
            if not cards:
                break

            for card in cards:
                try:
                    if not await card.query_selector(".money-discount"):
                        continue

                    title_el = await card.query_selector("#product-name")
                    if not title_el:
                        continue
                    title = (await title_el.inner_text()).strip()

                    href  = await title_el.get_attribute("href") or ""
                    full_url = f"https://www.migros.com.tr{href}"

                    img_tag = await card.query_selector("img.product-image")
                    img_url = ""
                    if img_tag:
                        img_url = await img_tag.get_attribute("data-src") or ""
                        if not img_url or "data:image" in img_url:
                            img_url = await img_tag.get_attribute("src") or ""

                    orig_el = await card.query_selector(".single-price-amount")
                    sale_el = await card.query_selector(".sale-price")
                    if not (orig_el and sale_el):
                        continue

                    orig = normalize_price(await orig_el.inner_text())
                    sale = normalize_price(await sale_el.inner_text())
                    pct  = round((orig - sale) / orig * 100)

                    local_img = await download_image(img_url, title)

                    products.append({
                        "title"            : title,
                        "url"              : full_url,
                        "image"            : local_img,
                        "store"            : "Migros",
                        "store_logo"       : "migros.png",
                        "category"         : "Market",
                        "original_price"   : f"{orig:.2f}",
                        "price"            : f"{sale:.2f}",
                        "discountPercentage": pct
                    })
                except Exception as e:
                    logging.warning(f"❌  Error parsing product: {e}")

            logging.info(f"✅  Page {page_no}: {len(products)} total so far.")
            page_no += 1

        await browser.close()
    return products

# -------------------------------------------------------------------- #
#  BACKEND PUSH  (new)
# -------------------------------------------------------------------- #
async def push_to_api(items: list[dict]) -> None:
    """POST scraped items to FastAPI backend."""
    if not items:
        return
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(API_ENDPOINT, json=items)
        r.raise_for_status()
        logging.info(f"🚀  Uploaded {len(items)} items for {items[0]['store']}")

# -------------------------------------------------------------------- #
#  LOCAL BACKUP  (optional)
# -------------------------------------------------------------------- #
def update_discounts_json(new_items: list[dict], store="Migros") -> None:
    logging.info(f"📦  Writing local backup to {OUTPUT_JSON}")
    try:
        existing = json.loads(OUTPUT_JSON.read_text("utf-8"))
    except Exception:
        existing = []
    existing = [p for p in existing if (p.get("store") != store)]
    existing.extend(new_items)
    OUTPUT_JSON.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    logging.info(f"✅  {len(existing)} total items in local discounts.json")
# --------------------------------------------------------------------------- #
#  JSON update utility
# --------------------------------------------------------------------------- #
def update_discounts_json(new_items: list[dict], store="Migros") -> None:
    logging.info(f"📦  Merging {len(new_items)} {store} items into {OUTPUT_JSON}")

    existing = []
    if OUTPUT_JSON.exists():
        try:
            existing = json.loads(OUTPUT_JSON.read_text("utf-8"))
        except json.JSONDecodeError:
            logging.warning("⚠️  discounts.json corrupted – starting fresh")

    # Drop older Migros entries
    existing = [p for p in existing if p.get("store") != store]
    existing.extend(new_items)
    OUTPUT_JSON.write_text(
    json.dumps(existing, ensure_ascii=False, indent=2),
    encoding="utf-8"
    )

    logging.info(f"✅  {len(existing)} total items now in discounts.json")

# --------------------------------------------------------------------------- #
#  Main
# --------------------------------------------------------------------------- #
async def main():
    items = await scrape_migros_discounts()
    if items:
        await push_to_api(items)          # ← primary path
        update_discounts_json(items)      # ← optional flat-file backup
    else:
        logging.warning("⚠️  No Migros discounts scraped.")

if __name__ == "__main__":
    asyncio.run(main())

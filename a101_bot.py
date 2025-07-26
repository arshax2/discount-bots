import asyncio
import json
import httpx
import os
import re
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright

API_ENDPOINT = "http://localhost:8000/api/discounts"
DATA_FILE = "discounts.json"
IMAGE_DIR = Path("../discount-frontend/public/images/a101")
STORE_NAME = "A101"

A101_URLS = [
    "https://www.a101.com.tr/kapida/haftanin-yildizlari/",
    "https://www.a101.com.tr/kapida/aldin-aldin/",
    "https://www.a101.com.tr/kapida/cok-al-az-ode/"
]

IMAGE_DIR.mkdir(parents=True, exist_ok=True)

def slugify(name):
    return re.sub(r'[^a-z0-9\-]', '', re.sub(r'\s+', '-', name.lower())).strip("-")

async def download_image(url, filename):
    filepath = IMAGE_DIR / filename
    if filepath.exists():
        return
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=15)
            if response.status_code == 200:
                with open(filepath, "wb") as f:
                    f.write(response.content)
                print(f"📸 Downloaded image → {filename}")
            else:
                print(f"⚠️ Failed to download image: {url}")
    except Exception as e:
        print(f"❌ Error downloading image: {e}")

async def parse_products_smooth_scroll(page):
    seen = set()
    results = []
    previous_count = 0
    scroll_attempts = 0

    while True:
        product_cards = await page.query_selector_all("div[class*=product-card], div.w-full.border.cursor-pointer")

        for item in product_cards:
            try:
                title_block = await item.query_selector("div.h-\\[120px\\].flex.pt-1.flex-col.justify-between")
                title = await title_block.inner_text() if title_block else ""
                if not title or title in seen:
                    continue
                seen.add(title)

                discounted_price_el = await item.query_selector("div.text-\\[\\#EA242A\\]")
                discounted_price = await discounted_price_el.inner_text() if discounted_price_el else ""

                original_price_el = await item.query_selector("div.line-through")
                original_price = await original_price_el.inner_text() if original_price_el else ""

                await item.scroll_into_view_if_needed()
                await page.wait_for_timeout(200)

                imgs = await item.query_selector_all("img")
                image_url = ""
                for img in imgs:
                    alt = await img.get_attribute("alt") or ""
                    src = await img.get_attribute("src") or ""
                    if not src.strip():
                        src = await img.get_attribute("data-src") or ""
                    if alt.strip().lower() in title.strip().lower() and (
                        ".jpg" in src or ".jpeg" in src or ".webp" in src or ".png" in src
                    ):
                        image_url = src
                        break

                image_slug = slugify(title)
                image_filename = f"{image_slug}.jpg"
                local_image_path = ""

                if image_url:
                    if not image_url.startswith("http"):
                        image_url = f"https://www.a101.com.tr/{image_url.lstrip('/')}"
                    await download_image(image_url, image_filename)
                    local_image_path = f"/images/a101/{image_filename}"
                else:
                    print(f"🚫 Skipped image for: {title}")
                    inner_html = await item.inner_html()
                    with open("debug_missing_image.html", "w", encoding="utf-8") as f:
                        f.write(inner_html)

                url = await item.query_selector("a")
                url = await url.get_attribute("href") if url else ""
                url = f"https://www.a101.com.tr{url}"

                if discounted_price and title:
                    product = {
                        "name": title.strip(),
                        "url": url,
                        "image": local_image_path,
                        "original_price": original_price.strip().replace("₺", "").replace(",", "."),
                        "price": discounted_price.strip().replace("₺", "").replace(",", "."),
                        "store": STORE_NAME,
                        "source": STORE_NAME,
                        "category": "Market",
                        "discountPercentage": calculate_discount(original_price, discounted_price),
                        "timestamp": datetime.now().isoformat()
                    }
                    results.append(product)
                    print(f"✅ {title.strip()} - {product['price']}₺")

            except Exception as e:
                print("❌ Error parsing item:", e)

        await page.evaluate("window.scrollBy(0, 400)")
        await page.wait_for_timeout(1000)

        if len(seen) == previous_count:
            scroll_attempts += 1
        else:
            scroll_attempts = 0
            previous_count = len(seen)

        if scroll_attempts >= 5:
            break

    print(f"🎯 Total parsed products: {len(results)}")
    return results

def calculate_discount(original, discounted):
    try:
        o = float(original.strip().replace("₺", "").replace(",", "."))
        d = float(discounted.strip().replace("₺", "").replace(",", "."))
        return round(100 * (o - d) / o)
    except:
        return None

async def save_json(new_data):
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            existing = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        existing = []

    updated = [item for item in existing if item["store"] != STORE_NAME]
    updated.extend(new_data)

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(updated, f, ensure_ascii=False, indent=2)

    print(f"📁 Saved {len(new_data)} new {STORE_NAME} items. Total in file: {len(updated)}")

async def post_to_backend(data):
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(API_ENDPOINT, json=data)
            if response.status_code == 200:
                print("🚀 Data posted to backend successfully")
            else:
                print("⚠️ Backend error:", response.text)
    except Exception as e:
        print("❌ POST request failed:", e)

async def scrape_a101():
    print("🛒 A101 Bot Started")
    all_products = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=[
                "--use-fake-ui-for-media-stream",
                "--disable-geolocation",
                "--disable-notifications",
                "--disable-popup-blocking"
            ]
        )

        context = await browser.new_context(
            permissions=[],
            geolocation=None,
            locale="en-US",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        # ✅ Explicitly deny permissions for the domain
        await context.grant_permissions([], origin="https://www.a101.com.tr")

        page = await context.new_page()

        for url in A101_URLS:
            print(f"🌐 Visiting: {url}")
            try:
                if "aldin-aldin" in url:
                    await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                    print("⏱️ Loaded with DOMContentLoaded to avoid timeout.")
                else:
                    await page.goto(url, timeout=60000)
                    await page.wait_for_load_state("networkidle")
                    print("✅ Loaded with NetworkIdle.")

                try:
                    await page.wait_for_selector("button:has-text('KABUL ET')", timeout=5000)
                    await page.click("button:has-text('KABUL ET')")
                    print("🍪 Cookie consent dismissed.")
                except:
                    print("🍪 Cookie popup not found.")

                await page.wait_for_selector("div[class*=product-card], div.w-full.border.cursor-pointer", timeout=10000)

                products = await parse_products_smooth_scroll(page)

                if len(products) == 0:
                    await page.screenshot(path="debug_a101_screenshot.png", full_page=True)
                    html = await page.content()
                    with open("debug_a101.html", "w", encoding="utf-8") as f:
                        f.write(html)
                    print("🧪 No products found — saved debug files.")
                else:
                    print(f"✅ Parsed {len(products)} products from page")
                    all_products.extend(products)

            except Exception as e:
                print(f"❌ Failed on {url}:", e)

        await browser.close()

    await save_json(all_products)
    await post_to_backend(all_products)

if __name__ == "__main__":
    asyncio.run(scrape_a101())

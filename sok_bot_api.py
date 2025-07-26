import os
import json
import asyncio
import httpx
from pathlib import Path
from playwright.async_api import async_playwright

IMAGE_DIR = Path("../discount-frontend/public/images/sok/")
DATA_FILE = Path("discounts.json")
FASTAPI_ENDPOINT = "http://localhost:8000/api/discounts"

API_URL = "https://www.sokmarket.com.tr/api/v1/search"
PARAMS_TEMPLATE = {
    "cat": 10,
    "sort": "SCORE_DESC",
    "page": 1,
    "size": 20,
    "pgt": "CATEGORY_LISTING"
}

def calculate_discount(old, new):
    try:
        return round((1 - (new / old)) * 100)
    except:
        return 0

def safe_float(value):
    try:
        return float(str(value).replace(",", ".").replace("₺", "").strip())
    except:
        return None

async def download_image_with_retry(client, url, image_path, name, retries=3):
    for attempt in range(1, retries + 1):
        try:
            res = await client.get(url, timeout=10)
            if res.status_code == 200:
                with open(image_path, "wb") as f:
                    f.write(res.content)
                return True
        except:
            await asyncio.sleep(1)
    print(f"⚠️ Failed to download image for: {name}")
    return False

async def get_session_headers_from_browser():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        print("🧭 Launching browser and visiting Şok Market...")
        await page.goto("https://www.sokmarket.com.tr/market-c-10", timeout=60000)
        await page.wait_for_timeout(3000)

        cookies = await context.cookies()
        cookie_header = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
        cookie_dict = {c["name"]: c["value"] for c in cookies}

        headers = {
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://www.sokmarket.com.tr/market-c-10",
            "Origin": "https://www.sokmarket.com.tr",
            "x-app-version": "3dc7f4ee",
            "x-platform": "WEB",
            "x-service-type": "MARKET",
            "x-store-id": cookie_dict.get("X-Store-Id", "13412"),
            "x-ecommerce-deviceid": cookie_dict.get("X-Ecommerce-Deviceid", ""),
            "x-ecommerce-sid": cookie_dict.get("X-Ecommerce-Sid", ""),
            "cookie": cookie_header
        }

        await browser.close()
        print("✅ Session headers built.")
        return headers

async def fetch_discounted_products(headers):
    os.makedirs(IMAGE_DIR, exist_ok=True)
    page = 1
    all_products = []

    async with httpx.AsyncClient() as client:
        while True:
            print(f"🔄 Fetching page {page}...")
            params = PARAMS_TEMPLATE.copy()
            params["page"] = page

            res = await client.get(API_URL, headers=headers, params=params)
            if res.status_code != 200:
                print(f"❌ API error {res.status_code}")
                break

            data = res.json()
            items = data.get("results", [])
            if not items:
                print("✅ No more products.")
                break

            for item in items:
                name = item.get("product", {}).get("name", "").strip()
                url_path = item.get("product", {}).get("path", "")
                url = f"https://www.sokmarket.com.tr/urun/{url_path}"

                image_obj = item.get("product", {}).get("images", [])
                image_url = None
                if image_obj:
                    host = image_obj[0].get("host", "")
                    path = image_obj[0].get("path", "")
                    if host and path:
                        image_url = f"{host}/{path}"

                new_price = safe_float(item.get("prices", {}).get("discounted", {}).get("value"))
                old_price = safe_float(item.get("prices", {}).get("original", {}).get("value"))

                if old_price is None or new_price is None or new_price >= old_price:
                    continue

                discount_percent = calculate_discount(old_price, new_price)
                image_name = f"{name[:40].replace(' ', '_')}.jpg"
                image_path = IMAGE_DIR / image_name

                if not await download_image_with_retry(client, image_url, image_path, name):
                    continue

                all_products.append({
                    "name": name,
                    "url": url,
                    "image": f"/images/sok/{image_name}",
                    "store": "Şok",
                    "store_logo": "sokmarket.png",
                    "source": "Şok",
                    "category": "Market",
                    "price": f"{new_price:.2f}",
                    "original_price": f"{old_price:.2f}",
                    "discountPercentage": discount_percent
                })

            page += 1

    print(f"✅ Collected {len(all_products)} discounted products from Şok.")
    return all_products

async def update_json_and_post(products):
    if not products:
        print("⚠️ No products to save/post.")
        return

    if DATA_FILE.exists():
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            existing = json.load(f)
    else:
        existing = []

    others = [p for p in existing if p["store"] != "Şok"]
    merged = others + products

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    print("💾 discounts.json updated.")

    try:
        async with httpx.AsyncClient() as client:
            res = await client.post(FASTAPI_ENDPOINT, json=products)
            if res.status_code == 200:
                print("📡 Data successfully posted to backend.")
            else:
                print(f"⚠️ Backend POST failed: {res.status_code} - {res.text}")
    except Exception as e:
        print("❌ Error posting to backend:", e)

async def main():
    try:
        headers = await get_session_headers_from_browser()
        products = await fetch_discounted_products(headers)
        await update_json_and_post(products)
    except Exception as e:
        print("❌ Unexpected error:", e)

if __name__ == "__main__":
    asyncio.run(main())

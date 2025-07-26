# sok_bot_api.py

import os
import json
import httpx
from pathlib import Path

API_URL = "https://www.sokmarket.com.tr/api/v1/search"
IMAGE_DIR = Path("../discount-frontend/public/images/sok/")
DATA_FILE = Path("discounts.json")
FASTAPI_ENDPOINT = "http://localhost:8000/api/discounts"

HEADERS = {
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0"
}

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

async def fetch_products():
    os.makedirs(IMAGE_DIR, exist_ok=True)
    page = 1
    all_products = []

    async with httpx.AsyncClient() as client:
        while True:
            print(f"🔄 Fetching page {page}...")
            params = PARAMS_TEMPLATE.copy()
            params["page"] = page

            response = await client.get(API_URL, headers=HEADERS, params=params)
            if response.status_code != 200:
                print(f"⚠️ Failed to fetch page {page}: {response.status_code}")
                break

            data = response.json()
            items = data.get("content", [])
            if not items:
                print("✅ No more products found. Stopping.")
                break

            for item in items:
                name = item.get("name")
                url = f"https://www.sokmarket.com.tr/urun/{item.get('url')}"
                image_url = item.get("images", [])[0].get("url") if item.get("images") else None
                new_price = item.get("price", {}).get("discounted", {}).get("amount")
                old_price = item.get("price", {}).get("original", {}).get("amount")

                if not old_price or not new_price or new_price >= old_price:
                    continue  # not discounted

                discount_percent = calculate_discount(old_price, new_price)
                image_name = f"{name[:40].replace(' ', '_')}.jpg"
                image_path = IMAGE_DIR / image_name

                try:
                    img_data = await client.get(image_url)
                    with open(image_path, "wb") as f:
                        f.write(img_data.content)
                except:
                    print(f"❌ Failed to download image for: {name}")
                    continue

                all_products.append({
                    "name": name,
                    "url": url,
                    "image": f"/images/sok/{image_name}",
                    "store": "Şok",
                    "source": "Şok",
                    "category": "Market",
                    "price": f"{new_price:.2f}",
                    "original_price": f"{old_price:.2f}",
                    "discountPercentage": discount_percent
                })

            page += 1

    print(f"✅ Collected {len(all_products)} discounted products from Şok")

    if not all_products:
        print("⚠️ No discounted products found.")
        return

    # Merge into discounts.json
    if DATA_FILE.exists():
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            existing = json.load(f)
    else:
        existing = []

    others = [p for p in existing if p["store"] != "Şok"]
    merged = others + all_products

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    print("💾 discounts.json updated.")

    # Post to backend
    try:
        async with httpx.AsyncClient() as client:
            res = await client.post(FASTAPI_ENDPOINT, json=all_products)
            if res.status_code == 200:
                print("📡 Data successfully posted to backend.")
            else:
                print(f"⚠️ Backend POST failed: {res.status_code} - {res.text}")
    except Exception as e:
        print("❌ Error posting to backend:", e)

if __name__ == "__main__":
    import asyncio
    asyncio.run(fetch_products())

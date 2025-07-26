import asyncio
import json
import logging
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)
BASE_URL = "https://www.migros.com.tr/tum-indirimli-urunler-dt-0"

async def log_json_api(resp):
    headers = resp.headers
    content_type = headers.get("content-type", "")
    if "application/json" in content_type:
        url = resp.url
        text = await resp.text()
        if '"products"' in text or '"campaign"' in text:  # adjust filter keywords
            logging.info(f"🔍 Found product API call: {url}")
            with open("migros_products.json", "w", encoding="utf-8") as f:
                json.dump({"url": url, "body": json.loads(text)}, f, ensure_ascii=False, indent=2)

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        page.on("response", lambda resp: asyncio.create_task(log_json_api(resp)))

        await page.goto(BASE_URL)
        await page.wait_for_timeout(5000)  # give time for XHR to finish
        await browser.close()

        logging.info("⚠️ Completed interception. Check migros_products.json")

if __name__ == "__main__":
    asyncio.run(main())

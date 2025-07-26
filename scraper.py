import asyncio
import json
import logging
import schedule
import time

# ✅ Import bots with alias fallback if original name differs
from a101_bot import scrape_page as scrape_a101
from migros_bot import scrape_page as scrape_migros
from sokmarket_bot import scrape_page as scrape_sokmarket
from carrefoursa_bot import run as scrape_carrefour

import httpx

# ✅ Logging setup
logging.basicConfig(
    filename="scraper.log",
    filemode="a",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# ✅ Run all bots
async def run_all_bots():
    try:
        logging.info("🚀 Starting all discount scrapers...")

        # Run Playwright/async bots
        a101_data = await scrape_a101()
        migros_data = await scrape_migros()
        sok_data = await scrape_sokmarket()

        # Run Selenium bot (CarrefourSA)
        carrefour_data = scrape_carrefour()

        all_products = a101_data + migros_data + sok_data + carrefour_data
        logging.info(f"✅ Total collected products: {len(all_products)}")

        # Save to file
        with open("all_discounted_products.json", "w", encoding="utf-8") as f:
            json.dump(all_products, f, ensure_ascii=False, indent=4)
        logging.info("💾 Data saved to all_discounted_products.json")

        # ✅ Post to FastAPI backend in chunks
        await post_to_api_in_chunks(all_products)

    except Exception as e:
        logging.error(f"❌ Error during scraping: {e}")

# ✅ Chunked POST to avoid timeout
async def post_to_api_in_chunks(data, chunk_size=100):
    api_url = "http://localhost:8000/api/discounts"
    async with httpx.AsyncClient(timeout=30.0) as client:
        for i in range(0, len(data), chunk_size):
            chunk = data[i:i+chunk_size]
            try:
                response = await client.post(api_url, json=chunk)
                if response.status_code == 200:
                    logging.info(f"✅ Chunk {i//chunk_size + 1} posted successfully.")
                else:
                    logging.error(f"❌ Chunk {i//chunk_size + 1} failed with status {response.status_code}")
            except Exception as e:
                logging.error(f"❌ Chunk {i//chunk_size + 1} failed: {e}")

# ✅ Scheduler job wrapper
def job():
    logging.info("🕒 Scheduled job triggered.")
    asyncio.run(run_all_bots())

# ⏰ Schedule setup: run every 6 hours
schedule.every(6).hours.do(job)

# ✅ Run once at startup, then loop
if __name__ == "__main__":
    logging.info("📅 Scraper scheduler started.")
    job()  # Initial run
    while True:
        schedule.run_pending()
        time.sleep(60)

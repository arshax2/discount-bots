# main.py
import asyncio

from bots.a101_bot import scrape_a101
from bots.carrefoursa_bot import scrape_carrefour
from bots.migros_bot import scrape_migros
from bots.sok_bot import scrape_sok

async def run_all_bots():
    print("🚀 Running all bots...")
    await asyncio.gather(
        scrape_a101(),
        scrape_carrefour(),
        scrape_migros(),
        scrape_sok(),
    )
    print("✅ All bots finished.")

if __name__ == "__main__":
    asyncio.run(run_all_bots())

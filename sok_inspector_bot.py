# sok_inspector_bot.py

import asyncio
from playwright.async_api import async_playwright

async def scroll_to_bottom(page):
    previous_height = 0
    for i in range(60):  # deep scroll
        current_height = await page.evaluate("document.body.scrollHeight")
        if current_height == previous_height:
            break
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(1500)
        previous_height = current_height

async def dismiss_popups(page):
    try:
        cookie_btn = await page.query_selector("button#onetrust-accept-btn-handler")
        if cookie_btn:
            await cookie_btn.click()
            print("🍪 Cookie popup dismissed.")
        await page.wait_for_timeout(1000)
    except:
        pass

async def inspect_products():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        print("🛒 Opening Şok Market...")
        await page.goto("https://www.sokmarket.com.tr/market-c-10", timeout=60000)
        await page.wait_for_load_state("networkidle")
        await dismiss_popups(page)
        await scroll_to_bottom(page)

        print("🔍 Looking for real product cards...")

        cards = await page.query_selector_all("div[class*=ProductCard-module_card__]")
        print(f"📦 Found {len(cards)} product cards")

        for card in cards:
            html = await card.inner_html()

            if "line-through" in html and "EA242A" in html:
                print("\n✅ Found a discounted product card!")

                title_el = await card.query_selector("div.line-clamp-3")
                price_new_el = await card.query_selector("span[class*='EA242A']")
                price_old_el = await card.query_selector("span.line-through")
                img_el = await card.query_selector("img")

                print("\n📦 Extracted Class Info:")
                print("Title class:", await title_el.get_attribute("class") if title_el else "Not found")
                print("Price (new) class:", await price_new_el.get_attribute("class") if price_new_el else "Not found")
                print("Price (old) class:", await price_old_el.get_attribute("class") if price_old_el else "Not found")
                print("Image class:", await img_el.get_attribute("class") if img_el else "Not found")

                outer_html = await card.evaluate("el => el.outerHTML")
                print("\n🔍 Sample outerHTML:\n", outer_html[:1000], "...\n")
                break

        await browser.close()

if __name__ == "__main__":
    asyncio.run(inspect_products())

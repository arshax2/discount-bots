from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import requests
import time
import json
import os

CHROMEDRIVER_PATH = "C:\\Users\\main0\\chromedriver.exe"
BASE_URL = "https://www.carrefoursa.com"
API_URL = "http://localhost:8000/api/discounts"
DATA_FILE = DATA_FILE = "discounts.json"
STORE_NAME = "CarrefourSA"

CATEGORIES = [
    "https://www.carrefoursa.com/meyve-sebze/c/1014",
    "https://www.carrefoursa.com/et-tavuk-balik/c/1044",
    "https://www.carrefoursa.com/sut-urunleri/c/1310",
    "https://www.carrefoursa.com/kahvaltilik-urunler/c/1363",
    "https://www.carrefoursa.com/temel-gida/c/1110",
    "https://www.carrefoursa.com/atistirmalik/c/1493",
    "https://www.carrefoursa.com/hazir-yemek-donuk-urunler/c/1064",
    "https://www.carrefoursa.com/firin/c/1275",
    "https://www.carrefoursa.com/icecekler/c/1409",
    "https://www.carrefoursa.com/saglikli-yasam/c/1938",
    "https://www.carrefoursa.com/dondurma/c/1260",
    "https://www.carrefoursa.com/bebek-dunyasi/c/1846",
    "https://www.carrefoursa.com/pet-shop/c/2054",
    "https://www.carrefoursa.com/temizlik-deterjan/c/1556",
    "https://www.carrefoursa.com/kagit-kozmetik/c/1674",
    "https://www.carrefoursa.com/elektronik/c/2286",
    "https://www.carrefoursa.com/ev-yasam/c/2188",
]

options = Options()
options.add_argument("--headless=new")
options.add_argument("--window-size=1920,1080")
driver = webdriver.Chrome(service=Service(CHROMEDRIVER_PATH), options=options)
wait = WebDriverWait(driver, 10)

def scroll_to_bottom():
    last_height = driver.execute_script("return document.body.scrollHeight")
    while True:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1.5)
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height

def extract_price_from_outerhtml(html):
    soup = BeautifulSoup(html, "html.parser")

    try:
        orig = soup.select_one(".priceLineThrough")
        original = orig.get_text(strip=True).replace("TL", "") if orig else None
        original = original.replace(",", ".") if original else None
    except:
        original = None

    try:
        disc = soup.select_one(".item-price")
        discounted = disc.get_text(strip=True).replace("TL", "") if disc else None
        discounted = discounted.replace(",", ".") if discounted else None
    except:
        discounted = None

    return original, discounted

def merge_and_save(new_products):
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            existing = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        existing = []

    updated = [item for item in existing if item.get("store") != STORE_NAME]
    updated.extend(new_products)

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(updated, f, ensure_ascii=False, indent=2)

    print(f"📁 Saved {len(new_products)} new CarrefourSA items. Total in file: {len(updated)}")
    return updated

def run_scraper():
    all_products = []

    for category in CATEGORIES:
        print(f"🔎 Scanning category: {category}")
        driver.get(category)
        scroll_to_bottom()
        time.sleep(2)

        products = driver.find_elements(By.CLASS_NAME, "hover-box")
        print(f"📦 Found {len(products)} discounted products")

        for product in products:
            try:
                name = product.find_element(By.CLASS_NAME, "item-name").text.strip()
                url = product.find_element(By.TAG_NAME, "a").get_attribute("href")
                img = product.find_element(By.TAG_NAME, "img").get_attribute("src")

                html = product.get_attribute("outerHTML")
                original_price, discounted_price = extract_price_from_outerhtml(html)

                try:
                    op = float(original_price)
                    dp = float(discounted_price)
                    discount = round(((op - dp) / op) * 100)
                except:
                    discount = None

                if discount:
                    all_products.append({
                        "name": name,
                        "url": url,
                        "image": img,
                        "store": STORE_NAME,
                        "source": STORE_NAME,
                        "category": "Market",
                        "original_price": original_price,
                        "price": discounted_price,
                        "discountPercentage": discount
                    })

                    print(f"🧾 {name} | {original_price} → {discounted_price} | %{discount}")
            except Exception as e:
                continue

    print(f"\n📝 Merging {len(all_products)} items and posting to backend...")
    updated = merge_and_save(all_products)

    try:
        res = requests.post(API_URL, json=updated, timeout=60)
        if res.status_code == 200:
            print("✅ Successfully posted merged data to backend")
        else:
            print(f"❌ Failed to post to backend: {res.status_code}")
    except Exception as e:
        print("❌ Error posting to backend:", e)

    return updated

if __name__ == "__main__":
    run_scraper()
    driver.quit()

import json
import os
import random
import time
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright
import requests as standard_requests
from flask import Flask
from threading import Thread

# ============ MINI-WEBSERVER FÜR RENDER (KEEP-ALIVE) ============
app = Flask('')

@app.route('/')
def home():
    return "Vinted Snipe Bot is running 24/7!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.daemon = True
    t.start()
# ================================================================

# ============ KONFIGURATION ============
CONFIG = {
    "domain": "www.vinted.de",
    "search_text": "Nike Air Force 1",
    "price_from": None,
    "price_to": 60,
    "size_filter": "42",
    "discord_webhook_url": "https://discord.com/api/webhooks/1533547739546386533/gEn5ApJrKK1lNnG3yvVoykUNH3D0ecW2eLLimMfo97hFvxV1tD9_pyBuhZxqAGPoDSNV",
    "poll_interval_seconds": 45,
    "seen_items_file": "vinted_seen_items.json",
}
# ========================================

def load_seen_items(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()

def save_seen_items(path, seen_items, max_keep=2000):
    items_to_save = list(seen_items)[-max_keep:]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(items_to_save, f)

def matches_size(item, size_filter):
    if not size_filter:
        return True
    size_title = (item.get("size_title") or "").strip().lower()
    return size_filter.strip().lower() in size_title

def send_discord_notification(webhook_url, item, domain):
    item_url = f"https://{domain}/items/{item['id']}"
    photo_info = item.get("photo") or {}
    photo_url = photo_info.get("url")

    price_data = item.get("price")
    if isinstance(price_data, dict):
        price_str = f"{price_data.get('amount', '?')} {price_data.get('currency_code', 'EUR')}"
    elif price_data is not None:
        price_str = f"{price_data} EUR"
    else:
        price_str = "Unknown"

    user = item.get("user") or {}
    username = user.get("login", "Unknown")
    user_photo = user.get("photo", {}).get("url") if user.get("photo") else None
    
    feedback_positive = user.get("feedback_positive_count", 0)
    rating_stars = "⭐" * min(int(feedback_positive), 5) if feedback_positive else "⭐⭐⭐⭐⭐ (0)"

    status_str = item.get("status", "Unknown")
    title = item.get("title", "New Vinted Item")
    brand = item.get("brand_title", "Unknown")
    size = item.get("size_title", "Unknown")

    embed = {
        "title": title,
        "url": item_url,
        "color": 0x09B1BA,
        "author": {
            "name": username,
            "icon_url": user_photo if user_photo else "https://static.vinted.net/assets/profile-icon-default-xxxx.png"
        },
        "fields": [
            {"name": "⏳ Published", "value": "Just now", "inline": True},
            {"name": "🏷️ Brand", "value": brand, "inline": True},
            {"name": "📏 Size", "value": size, "inline": True},
            {"name": "🌟 Rating", "value": f"{rating_stars}", "inline": True},
            {"name": "💎 Condition", "value": status_str, "inline": True},
            {"name": "💰 Price", "value": price_str, "inline": True},
        ],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if photo_url:
        embed["image"] = {"url": photo_url}

    try:
        standard_requests.post(webhook_url, json={"embeds": [embed]}, timeout=15)
    except Exception as e:
        print(f"[!] Error sending Discord notification: {e}")

def main():
    cfg = CONFIG
    seen_items = load_seen_items(cfg["seen_items_file"])
    print(f"[i] Starting Playwright browser monitor for '{cfg['search_text']}'...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        first_run = True

        while True:
            try:
                page.goto(f"https://{cfg['domain']}", timeout=30000)
                page.wait_for_timeout(3000)

                search_url = f"https://{cfg['domain']}/api/v2/catalog/items?search_text={cfg['search_text']}&per_page={cfg.get('per_page', 20)}&order=newest_first"
                if cfg["price_from"]:
                    search_url += f"&price_from={cfg['price_from']}"
                if cfg["price_to"]:
                    search_url += f"&price_to={cfg['price_to']}"

                response = page.goto(search_url, timeout=30000)
                
                if response and response.status == 200:
                    data = response.json()
                    items = data.get("items", [])

                    new_items = []
                    for item in items:
                        item_id = str(item["id"])
                        if item_id in seen_items:
                            continue
                        seen_items.add(item_id)
                        if matches_size(item, cfg["size_filter"]):
                            new_items.append(item)

                    if first_run:
                        print(f"[+] SUCCESS! {len(items)} items fetched via Browser. Monitoring is active!")
                        first_run = False
                    else:
                        for item in new_items:
                            print(f"[+] New match: {item.get('title')}")
                            send_discord_notification(cfg["discord_webhook_url"], item, cfg["domain"])

                    save_seen_items(cfg["seen_items_file"], seen_items)
                else:
                    print(f"[!] API-Fehler / Statuscode: {response.status if response else 'Unbekannt'}")

            except Exception as e:
                print(f"[!] Query error: {e}")

            sleep_time = cfg["poll_interval_seconds"] + random.uniform(2, 10)
            time.sleep(sleep_time)

if __name__ == "__main__":
    # Startet den Webserver im Hintergrund, damit Render den Web Service nicht stoppt
    keep_alive()
    # Startet die Bot-Hauptschleife
    main()
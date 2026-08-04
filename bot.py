import json
import os
import random
import time
from datetime import datetime, timezone
from curl_cffi import requests as cffi_requests
import requests as standard_requests
from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "Vinted Snipe Bot All is running 24/7!", 200

# ============ KONFIGURATION ============
CONFIG = {
    "domain": "www.vinted.de",
    "search_queries": [
        "Ralph Lauren", "Polo Ralph Lauren", "Nike", "Adidas", "Lacoste",
        "Tommy Hilfiger", "Carhartt", "Carhartt WIP", "Stüssy", "Supreme",
        "Stone Island", "CP Company", "The North Face", "Patagonia", "Arc'teryx",
        "Moncler", "Burberry", "Gucci", "Louis Vuitton", "Dior",
        "Balenciaga", "Palm Angels", "Off-White", "Essentials", "Fear of God",
        "New Balance", "ASICS", "Salomon", "Jordan", "Air Max",
        "Dunk", "Yeezy", "Samba", "Gazelle", "Bape",
        "Corteiz", "Trapstar", "Denim Tears", "Ami Paris", "Maison Margiela",
        "Canada Goose", "Alpha Industries", "Levi's", "Dickies", "G-Star",
        "Vintage", "Y2K", "Zip Hoodie", "Strickpullover", "Flared Jeans"
    ],
    "price_from": None,
    "price_to": 150,
    "size_filter": "", 
    "discord_webhook_url": os.environ.get("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/1533547739546386533/gEn5ApJrKK1lNnG3yvVoykUNH3D0ecW2eLLimMfo97hFvxV1tD9_pyBuhZxqAGPoDSNV"),
    "poll_interval_seconds": 30,
    "seen_items_file": "vinted_seen_items.json",
}
# ========================================

def load_seen_items(path):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except:
            return set()
    return set()

def save_seen_items(path, seen_items, max_keep=5000):
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

def search_worker():
    cfg = CONFIG
    seen_items = load_seen_items(cfg["seen_items_file"])
    print(f"[i] Starting background curl_cffi monitor for all 50 queries...")

    session = cffi_requests.Session(impersonate="chrome120")

    try:
        session.get(f"https://{cfg['domain']}", timeout=30)
        time.sleep(2)
    except Exception as e:
        print(f"[!] Warning on initial load: {e}")

    first_run = True

    while True:
        try:
            for query in cfg["search_queries"]:
                try:
                    search_url = f"https://{cfg['domain']}/api/v2/catalog/items?search_text={query}&per_page=15&order=newest_first"
                    if cfg["price_from"]:
                        search_url += f"&price_from={cfg['price_from']}"
                    if cfg["price_to"]:
                        search_url += f"&price_to={cfg['price_to']}"

                    response = session.get(search_url, timeout=30)
                    
                    if response.status_code == 200:
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

                        if not first_run:
                            for item in new_items:
                                print(f"[+] New match found for {query}: {item.get('title')}")
                                send_discord_notification(cfg["discord_webhook_url"], item, cfg["domain"])
                                time.sleep(1)

                        save_seen_items(cfg["seen_items_file"], seen_items)
                    else:
                        print(f"[!] API-Fehler für '{query}' / Statuscode: {response.status_code}")

                except Exception as e:
                    print(f"[!] Query error for '{query}': {e}")
                
                time.sleep(random.uniform(1.5, 3))

            if first_run:
                print("[+] SUCCESS! All initial items cached. Now actively monitoring...")
                first_run = False

            sleep_time = cfg["poll_interval_seconds"] + random.uniform(2, 5)
            time.sleep(sleep_time)
        except Exception as e:
            print(f"[!] Worker error: {e}")
            time.sleep(10)

if __name__ == "__main__":
    bot_thread = Thread(target=search_worker)
    bot_thread.daemon = True
    bot_thread.start()

    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

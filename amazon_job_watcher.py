#!/usr/bin/env python3
"""Watch amazon.jobs for new postings and send notifications via Telegram and/or ntfy.sh.

Setup:
  pip install requests

Telegram setup (2 minutes):
  1. In Telegram, message @BotFather -> /newbot -> copy the bot token.
  2. Open a chat with your new bot and send it any message (e.g. "hi").
  3. Run:  python amazon_job_watcher.py --get-chat-id   -> copy the chat ID.
  4. Paste both values below (or set TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID env vars).

Usage:
  python amazon_job_watcher.py                # check once (use with cron)
  python amazon_job_watcher.py --loop         # check every CHECK_EVERY_MINUTES
  python amazon_job_watcher.py --get-chat-id  # find your Telegram chat ID
  python amazon_job_watcher.py --test         # send a test notification
"""
import html
import json
import os
import sys
import time
from pathlib import Path

import requests

# ---------- CONFIG: edit these ----------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")  # from @BotFather
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")      # from --get-chat-id
NTFY_TOPIC = os.getenv("NTFY_TOPIC", "")                  # optional, leave "" to disable

SEARCH_PARAMS = {
    "base_query": "",   # keywords ("" for all jobs)
    "loc_query": "",        # location text
    "country": "USA",                    # 3-letter country code (optional)
    "sort": "recent",
    "result_limit": 25,
    "offset": 0,
}
CHECK_EVERY_MINUTES = 30
SEEN_FILE = Path(__file__).with_name("seen_jobs.json")
# ----------------------------------------

URL = "https://www.amazon.jobs/en/search.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (personal job alert script)"}


def load_seen() -> set:
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text()))
    return set()


def save_seen(seen: set) -> None:
    SEEN_FILE.write_text(json.dumps(sorted(seen)))


def fetch_jobs() -> list:
    r = requests.get(URL, params=SEARCH_PARAMS, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json().get("jobs", [])


def send_telegram(text_html: str) -> None:
    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
        return
    r = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text_html,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
        timeout=30,
    )
    if not r.ok:
        print("Telegram error:", r.text)


def send_ntfy(title: str, body: str, link: str = "") -> None:
    if not NTFY_TOPIC:
        return
    headers = {"Title": title.encode("utf-8"), "Tags": "briefcase"}
    if link:
        headers["Click"] = link
    requests.post(f"https://ntfy.sh/{NTFY_TOPIC}", data=body.encode("utf-8"),
                  headers=headers, timeout=30)


def notify(job: dict) -> None:
    title = job.get("title", "New Amazon job")
    location = job.get("normalized_location") or job.get("location", "")
    posted = job.get("posted_date", "n/a")
    link = "https://www.amazon.jobs" + job.get("job_path", "")

    send_telegram(
        f"🆕 <b>{html.escape(title)}</b>\n"
        f"📍 {html.escape(location)}\n"
        f"🗓 Posted: {html.escape(str(posted))}\n"
        f'<a href="{html.escape(link)}">View job</a>'
    )
    send_ntfy(title, f"{location}\nPosted: {posted}", link)


def get_chat_id() -> None:
    if not TELEGRAM_BOT_TOKEN:
        sys.exit("Set TELEGRAM_BOT_TOKEN first.")
    r = requests.get(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates", timeout=30)
    r.raise_for_status()
    chats = {u["message"]["chat"]["id"]: u["message"]["chat"].get("first_name", "")
             for u in r.json().get("result", []) if "message" in u}
    if not chats:
        sys.exit("No messages found. Send your bot a message in Telegram, then retry.")
    for cid, name in chats.items():
        print(f"Chat ID: {cid}  ({name})")


def check() -> None:
    seen = load_seen()
    first_run = not seen
    jobs = fetch_jobs()
    new = [j for j in jobs if str(j.get("id_icims") or j.get("id")) not in seen]

    for job in new:
        seen.add(str(job.get("id_icims") or job.get("id")))
        if not first_run:  # first run just records existing jobs
            notify(job)

    save_seen(seen)
    print(f"{time.strftime('%H:%M')} fetched {len(jobs)}, new {0 if first_run else len(new)}")


if __name__ == "__main__":
    if "--get-chat-id" in sys.argv:
        get_chat_id()
    elif "--test" in sys.argv:
        send_telegram("✅ Amazon job watcher test message")
        send_ntfy("Test", "Amazon job watcher is working")
        print("Test sent.")
    elif "--loop" in sys.argv:
        while True:
            try:
                check()
            except Exception as e:
                print("Error:", e)
            time.sleep(CHECK_EVERY_MINUTES * 60)
    else:
        check()

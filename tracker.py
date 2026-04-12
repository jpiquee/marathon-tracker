import requests
import json
import os
import sys

# === CONFIGURATION ===
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

EVENT_ID = "ASO-PARISMARATHON-2026"
PROFILE_ID = "RN4LKWXU"
TARGET_PACE_SEC = 341
TARGET_TIME_SEC = 4 * 3600
MARATHON_DIST = 42.195

API_URL = f"https://api.rtrt.me/events/{EVENT_ID}/profiles/{PROFILE_ID}/splits"
RTRT_APPID = "6163132b93ded769986f738b"
RTRT_TOKEN = "54EA6988C9EF05F8061A"
LAST_SPLIT_FILE = "last_split_count.txt"
LAST_UPDATE_FILE = "last_update_id.txt"


def format_time(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h}:{m:02d}:{s:02d}"


def format_pace(seconds_per_km):
    m = int(seconds_per_km // 60)
    s = int(seconds_per_km % 60)
    return f"{m}:{s:02d}"


def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": message[:4000], "parse

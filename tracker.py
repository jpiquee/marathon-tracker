import requests
import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

EVENT_ID = "ASO-PARISMARATHON-2026"
MARATHON_DIST = 42.195

RTRT_APPID = "6163132b93ded769986f738b"
RTRT_TOKEN = "54EA6988C9EF05F8061A"
LAST_UPDATE_FILE = "last_update_id.txt"

RUNNERS = [
    {"name": "Pomme", "pid": "R5N9G28S"},
]

DIST_MAP = {
    "START": 0, "5KM": 5, "10KM": 10, "15KM": 15,
    "20KM": 20, "21KM": 21.1, "25KM": 25, "28.8KM": 28.8,
    "30KM": 30, "35KM": 35, "40KM": 40, "42KM": 42.195,
    "FINISH": 42.195
}


def format_time(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return str(h) + ":" + str(m).zfill(2) + ":" + str(s).zfill(2)


def format_pace(seconds_per_km):
    m = int(seconds_per_km // 60)
    s = int(seconds_per_km % 60)
    return str(m) + ":" + str(s).zfill(2)


def send_telegram(message):
    url = "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": message[:4000]}
    try:
        r = requests.post(url, data=data, timeout=10)
        print("Telegram: " + str(r.status_code))
    except Exception as e:
        print("Erreur Telegram: " + str(e))


def get_file(name):
    try:
        with open(name, "r") as f:
            return f.read().strip()
    except:
        return ""


def save_file(name, value):
    with open(name, "w") as f:
        f.write(str(value))


def parse_time_to_seconds(time_str):
    parts = time_str.strip().split(":")
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    elif len(parts) == 2:
        return int(parts[0]) * 60 + float(parts[1])
    return 0


def get_dist_from_point(point_name):
    if point_name in DIST_MAP:
        return DIST_MAP[point_name]
    cleaned = point_name.replace("KM", "").replace("km", "").replace("K", "")
    try:
        return float(cleaned)
    except:
        return 0


def fetch_splits(pid):
    try:
        url = "https://api.rtrt.me/events/" + EVENT_ID + "/profiles/" + pid + "/splits"
        payload = {
            "appid": RTRT_APPID,
            "token": RTRT_TOKEN,
            "max": "2000",
            "loc": "1",
            "pidversion": "1",
            "etimes": "1",
            "units": "metric",
            "source": "webtracker"
        }
        r = requests.post(url, data=payload, timeout=15)
        data = r.json()
        return data.get("list", [])
    except Exception as e:
        print("Erreur API: " + str(e))
        return None


def compute_estimated_arrival(elapsed_sec_at_split, dist_km):
    """Calcule l'heure d'arrivee estimee depuis l'heure actuelle (pas depuis le split)."""
    if dist_km <= 0 or elapsed_sec_at_split <= 0:
        return None
    paris_tz = timezone(timedelta(hours=2))
    now = datetime.now(paris_tz)
    race_start = now.replace(hour=8, minute=40, second=0, microsecond=0)
    current_elapsed_sec = (now - race_start).total_seconds()
    if current_elapsed_sec <= 0:
        return None

    avg_pace_sec = elapsed_sec_at_split / dist_km  # sec/km a l'allure moyenne du split

    # Position estimee maintenant (on extrapole depuis le dernier split)
    time_since_split = max(0, current_elapsed_sec - elapsed_sec_at_split)
    estimated_dist_now = min(dist_km + time_since_split / avg_pace_sec, MARATHON_DIST)

    remaining_km = max(0, MARATHON_DIST - estimated_dist_now)
    remaining_sec = remaining_km * avg_pace_sec
    arrival = now + timedelta(seconds=remaining_sec)
    return arrival.strftime("%Hh%M")


def ai_analysis(splits_for_ai):
    if not ANTHROPIC_API_KEY:
        return None
    try:
        paris_tz = timezone(timedelta(hours=2))
        now = datetime.now(paris_tz)
        now_str = now.strftime("%Hh%M")
        race_start = now.replace(hour=8, minute=40, second=0, microsecond=0)
        elapsed_total = now - race_start
        elapsed_str = str(int(elapsed_total.total_seconds() // 3600)) + "h" + str(int((elapsed_total.total_seconds() % 3600) // 60)).zfill(2)

        headers = {
            "x-api-key": ANTHROPIC_API_KEY,
            "content-type": "application/json",
            "anthropic-version": "2023-06-01"
        }
        prompt = (
            "Coach marathon expert. Marathon de Paris 2026, depart 8h40. "
            "Il est actuellement " + now_str + " a Paris (temps ecoule depuis le depart : " + elapsed_str + "). "
            "IMPORTANT : les champs 'temps_ecoule' dans les splits sont des durees depuis le depart de la course (pas des heures d horloge). "
            "Splits de Pomme : " + json.dumps(splits_for_ai, ensure_ascii=False) + " "
            "En francais, max 300 car, emojis : analyse la tendance d allure, "
            "estime le temps final et l heure d arrivee (heure d horloge a Paris). "
            "Si elle a fini, felicite avec son temps."
        )
        body = {
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 280,
            "messages": [{"role": "user", "content": prompt}]
        }
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers, json=body, timeout=30
        )
        return r.json()["content"][0]["text"]
    except Exception as e:
        print("Erreur Claude: " + str(e))
        return None


def build_runner_status(runner_name, splits):
    if not splits:
        return runner_name + " : pas encore de donnees\n"

    last = splits[-1]
    label = last.get("label", last.get("point", "???"))
    point = last.get("point", "")
    time_str = last.get("time", "0")
    pace = last.get("kmPace", "N/A")
    pace_avg = last.get("kmPaceAvg", "N/A")
    etfp = last.get("etfp", "")

    elapsed_sec = parse_time_to_seconds(time_str)
    dist_km = get_dist_from_point(point)
    remaining_km = max(0, MARATHON_DIST - dist_km)

    est_finish = ""
    if etfp:
        parts = etfp.split("~")
        if len(parts) >= 2:
            est_finish = parts[1]

    progress_pct = min(100, (dist_km / MARATHON_DIST) * 100)
    bar_full = int(progress_pct / 10)
    bar = "=" * bar_full + "-" * (10 - bar_full)

    finished = "FINISH" in point.upper() or "ARRIVEE" in point.upper()

    if finished:
        header = "ARRIVEE " + runner_name + " !!!"
    else:
        header = runner_name + " - " + label

    lines = [
        header,
        "[" + bar + "] " + str(int(progress_pct)) + "%",
        "Parcouru : " + str(round(dist_km, 1)) + " / " + str(MARATHON_DIST) + " km",
        "Restant : " + str(round(remaining_km, 1)) + " km",
        "Duree : " + time_str.split(".")[0],
        "Allure segment : " + pace + " /km",
        "Allure moy : " + pace_avg + " /km",
    ]

    if not finished and est_finish:
        lines.append("Estimation arrivee : " + est_finish)

    return "\n".join(lines)


def build_full_message():
    runner = RUNNERS[0]
    splits = fetch_splits(runner["pid"])

    if splits is None:
        return runner["name"] + " : erreur API"

    message = build_runner_status(runner["name"], splits)

    splits_for_ai = None
    if splits:
        splits_for_ai = []
        for s in splits:
            p = s.get("point", "")
            t = s.get("time", "")
            pace = s.get("kmPace", "")
            pace_avg = s.get("kmPaceAvg", "")
            if p and t:
                splits_for_ai.append({
                    "point": p,
                    "temps_ecoule": t.split(".")[0],
                    "allure_km": pace,
                    "allure_moy": pace_avg,
                })

    if splits_for_ai:
        analysis = ai_analysis(splits_for_ai)
        if analysis:
            message += "\n\nAnalyse IA :\n" + analysis

    return message


def mode_auto():
    print("=== AUTO ===")
    msg = build_full_message()
    send_telegram(msg)
    print("Message envoye")


def mode_reply():
    print("=== REPLY ===")
    lu = get_file(LAST_UPDATE_FILE)
    last_update_id = int(lu) if lu else 0

    url = "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/getUpdates"
    try:
        r = requests.get(url, params={"offset": last_update_id + 1, "timeout": 0}, timeout=10)
        updates = r.json().get("result", [])
    except Exception as e:
        print("Erreur: " + str(e))
        return

    if not updates:
        print("Aucun message")
        return

    for update in updates:
        uid = update.get("update_id", 0)
        message = update.get("message", {})
        cid = str(message.get("chat", {}).get("id", ""))
        text = message.get("text", "").strip()

        if cid != TELEGRAM_CHAT_ID:
            save_file(LAST_UPDATE_FILE, uid)
            continue

        if text.startswith("/status"):
            msg = build_full_message()
            send_telegram(msg)

        save_file(LAST_UPDATE_FILE, uid)

    print("OK " + str(len(updates)) + " msg")


def mode_listen(duration_sec=3300):
    print("=== LISTEN " + str(duration_sec) + "s ===")
    lu = get_file(LAST_UPDATE_FILE)
    last_update_id = int(lu) if lu else 0
    end_time = time.time() + duration_sec

    while time.time() < end_time:
        remaining = int(end_time - time.time())
        poll_timeout = min(25, remaining)
        if poll_timeout <= 0:
            break
        try:
            url = "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/getUpdates"
            r = requests.get(
                url,
                params={"offset": last_update_id + 1, "timeout": poll_timeout},
                timeout=poll_timeout + 5
            )
            updates = r.json().get("result", [])
        except Exception as e:
            print("Erreur polling: " + str(e))
            time.sleep(5)
            continue

        for update in updates:
            uid = update.get("update_id", 0)
            message = update.get("message", {})
            cid = str(message.get("chat", {}).get("id", ""))
            text = message.get("text", "").strip()
            last_update_id = uid
            save_file(LAST_UPDATE_FILE, uid)

            if cid != TELEGRAM_CHAT_ID:
                continue

            if text.startswith("/status"):
                print("/status recu, envoi en cours...")
                msg = build_full_message()
                send_telegram(msg)

    print("Listen termine")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "auto"
    if mode == "reply":
        mode_reply()
    elif mode == "listen":
        duration = int(sys.argv[2]) if len(sys.argv) > 2 else 3300
        mode_listen(duration)
    else:
        mode_auto()

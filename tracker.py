import requests
import json
import os
import sys

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

EVENT_ID = "ASO-PARISMARATHON-2026"
TARGET_PACE_SEC = 341
TARGET_TIME_SEC = 14400
MARATHON_DIST = 42.195

RTRT_APPID = "6163132b93ded769986f738b"
RTRT_TOKEN = "54EA6988C9EF05F8061A"
LAST_UPDATE_FILE = "last_update_id.txt"

RUNNERS = [
    {"name": "Renaud", "pid": "RN4LKWXU"},
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


def ai_analysis(all_runners_data):
    if not ANTHROPIC_API_KEY:
        return None
    try:
        headers = {
            "x-api-key": ANTHROPIC_API_KEY,
            "content-type": "application/json",
            "anthropic-version": "2023-06-01"
        }
        prompt = (
            "Tu es un coach de marathon expert et enthousiaste. "
            "Voici les donnees EN COURS de coureurs au Marathon de Paris 2026. "
            "Objectif pour chacun : sub 4h (allure cible 5:41/km). Marathon = 42.195 km. "
            "Donnees : " + json.dumps(all_runners_data) + " "
            "Analyse en francais pour chaque coureur : "
            "estimation temps arrivee (tiens compte de la tendance d allure), "
            "est-il en bonne voie pour sub 4h, un petit mot d encouragement. "
            "Si un coureur a fini, felicite-le. "
            "Emojis. Max 600 caracteres total."
        )
        body = {
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 500,
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

    target_at_dist = dist_km * TARGET_PACE_SEC
    diff_sec = elapsed_sec - target_at_dist

    if diff_sec > 0:
        diff_line = "Retard : +" + format_time(abs(diff_sec))
    else:
        diff_line = "Avance : -" + format_time(abs(diff_sec))

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
        if elapsed_sec < TARGET_TIME_SEC:
            header += " SUB 4H !!!"
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
        diff_line,
    ]

    if not finished and est_finish:
        lines.append("Estimation arrivee : " + est_finish)

    if diff_sec > 120 and not finished:
        lines.append("ALERTE RETARD " + str(int(diff_sec / 60)) + " min !")

    return "\n".join(lines)


def build_full_message():
    all_runners_data = []
    sections = []

    for runner in RUNNERS:
        splits = fetch_splits(runner["pid"])
        if splits is None:
            sections.append(runner["name"] + " : erreur API")
            continue

        status = build_runner_status(runner["name"], splits)
        sections.append(status)

        if splits:
            summary = []
            for s in splits:
                summary.append({
                    "point": s.get("point", ""),
                    "time": s.get("time", ""),
                    "pace": s.get("kmPace", ""),
                    "paceAvg": s.get("kmPaceAvg", ""),
                    "etfp": s.get("etfp", "")
                })
            all_runners_data.append({
                "name": runner["name"],
                "splits": summary
            })

    separator = "\n" + "---" + "\n"
    message = separator.join(sections)
    message += "\n(Objectif : sub 4h00)"

    analysis = ai_analysis(all_runners_data)
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
        cid = str(update.get("message", {}).get("chat", {}).get("id", ""))

        if cid != TELEGRAM_CHAT_ID:
            save_file(LAST_UPDATE_FILE, uid)
            continue

        msg = build_full_message()
        send_telegram(msg)
        save_file(LAST_UPDATE_FILE, uid)

    print("OK " + str(len(updates)) + " msg")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "auto"
    if mode == "reply":
        mode_reply()
    else:
        mode_auto()

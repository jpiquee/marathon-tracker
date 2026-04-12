import requests
import json
import os
import sys

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

EVENT_ID = "ASO-PARISMARATHON-2026"
PROFILE_ID = "RN4LKWXU"
TARGET_PACE_SEC = 341
TARGET_TIME_SEC = 14400
MARATHON_DIST = 42.195

API_URL = "https://api.rtrt.me/events/" + EVENT_ID + "/profiles/" + PROFILE_ID + "/splits"
RTRT_APPID = "6163132b93ded769986f738b"
RTRT_TOKEN = "54EA6988C9EF05F8061A"
LAST_SPLIT_FILE = "last_split_count.txt"
LAST_UPDATE_FILE = "last_update_id.txt"

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


def fetch_splits():
    try:
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
        r = requests.post(API_URL, data=payload, timeout=15)
        data = r.json()
        print("API status: " + str(r.status_code))
        splits = data.get("list", [])
        if not splits:
            print("Reponse: " + r.text[:500])
        return splits
    except Exception as e:
        print("Erreur API: " + str(e))
        return None


def get_dist_from_point(point_name):
    if point_name in DIST_MAP:
        return DIST_MAP[point_name]
    cleaned = point_name.replace("KM", "").replace("km", "").replace("K", "")
    try:
        return float(cleaned)
    except:
        return 0


def ai_analysis(splits_data, is_final):
    if not ANTHROPIC_API_KEY:
        return None
    try:
        headers = {
            "x-api-key": ANTHROPIC_API_KEY,
            "content-type": "application/json",
            "anthropic-version": "2023-06-01"
        }
        if is_final:
            prompt = (
                "Tu es un commentateur de marathon enthousiaste. "
                "Voici les donnees COMPLETES de Renaud Carbonnier au Marathon de Paris 2026. "
                "Objectif : sub 4h (allure cible 5:41/km). "
                "Splits : " + json.dumps(splits_data) + " "
                "Resume final en francais : objectif atteint ou non, gestion de course, "
                "felicitations. Utilise des emojis. Max 500 caracteres."
            )
        else:
            prompt = (
                "Tu es un coach de marathon expert. "
                "Voici les donnees EN COURS de Renaud Carbonnier au Marathon de Paris 2026. "
                "Objectif : sub 4h (allure cible 5:41/km). Marathon = 42.195 km. "
                "Splits : " + json.dumps(splits_data) + " "
                "Analyse en francais : estimation temps arrivee (tiens compte de la tendance "
                "d allure, accelere-t-il ou ralentit-il), est-il en bonne voie pour sub 4h, "
                "conseil. Emojis. Max 400 caracteres."
            )
        body = {
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 400,
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


def build_status_message(splits, is_new_split):
    if not splits:
        return None

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

    # Avance / retard
    target_at_dist = dist_km * TARGET_PACE_SEC
    diff_sec = elapsed_sec - target_at_dist

    if diff_sec > 0:
        diff_line = "RETARD : +" + format_time(abs(diff_sec))
    else:
        diff_line = "AVANCE : -" + format_time(abs(diff_sec))

    # Estimation RTRT
    est_finish = ""
    if etfp:
        parts = etfp.split("~")
        if len(parts) >= 2:
            est_finish = parts[1]

    # Progression
    progress_pct = min(100, (dist_km / MARATHON_DIST) * 100)
    bar_full = int(progress_pct / 10)
    bar = "=" * bar_full + "-" * (10 - bar_full)

    if is_new_split:
        header = "NOUVEAU PASSAGE : " + label
    else:
        header = "STATUT RENAUD : " + label

    lines = [
        header,
        "",
        "[" + bar + "] " + str(int(progress_pct)) + "%",
        "",
        "Parcouru : " + str(round(dist_km, 1)) + " km / " + str(MARATHON_DIST) + " km",
        "Restant : " + str(round(remaining_km, 1)) + " km",
        "Duree : " + time_str.split(".")[0],
        "Allure segment : " + pace + " /km",
        "Allure moyenne : " + pace_avg + " /km",
        diff_line,
        "Estimation arrivee (RTRT) : " + est_finish,
        "(Objectif : sub 4h00)"
    ]

    if diff_sec > 120:
        lines.append("")
        lines.append("ALERTE : retard de " + str(int(diff_sec / 60)) + " min !")

    message = "\n".join(lines)

    # Analyse IA
    splits_summary = []
    for s in splits:
        splits_summary.append({
            "point": s.get("point", ""),
            "label": s.get("label", ""),
            "time": s.get("time", ""),
            "pace": s.get("kmPace", ""),
            "paceAvg": s.get("kmPaceAvg", ""),
            "splitTime": s.get("splitTime", ""),
            "etfp": s.get("etfp", "")
        })
    analysis = ai_analysis(splits_summary, False)
    if analysis:
        message += "\n\nAnalyse IA :\n" + analysis

    return message


def build_finish_message(splits):
    last = splits[-1]
    time_str = last.get("time", "0")
    final_sec = parse_time_to_seconds(time_str)
    pace_avg = last.get("kmPaceAvg", "N/A")

    if final_sec < TARGET_TIME_SEC:
        sub4 = "OUI !!!"
    else:
        sub4 = "Non"

    lines = [
        "ARRIVEE DE RENAUD !!!",
        "",
        "Temps final : " + time_str.split(".")[0],
        "Sub 4h : " + sub4,
        "Allure moyenne : " + pace_avg + " /km",
        "Distance : " + str(MARATHON_DIST) + " km"
    ]

    message = "\n".join(lines)

    splits_summary = []
    for s in splits:
        splits_summary.append({
            "point": s.get("point", ""),
            "label": s.get("label", ""),
            "time": s.get("time", ""),
            "pace": s.get("kmPace", ""),
            "paceAvg": s.get("kmPaceAvg", ""),
            "splitTime": s.get("splitTime", "")
        })
    analysis = ai_analysis(splits_summary, True)
    if analysis:
        message += "\n\nResume IA :\n" + analysis

    return message


def is_finished(splits):
    if not splits:
        return False
    last = splits[-1]
    point = last.get("point", "").upper()
    return "FINISH" in point or "ARRIVEE" in point


def mode_auto():
    print("=== AUTO ===")
    splits = fetch_splits()

    if splits is None:
        send_telegram("Erreur : impossible de contacter RTRT.me")
        return
    if not splits:
        lc = get_file(LAST_SPLIT_FILE)
        if lc and int(lc) > 0:
            send_telegram("Aucun nouveau passage detecte !")
        else:
            print("Pas encore de donnees")
        return

    current_count = len(splits)
    lc = get_file(LAST_SPLIT_FILE)
    last_count = int(lc) if lc else 0

    if current_count <= last_count:
        print("Pas de nouveau split (" + str(current_count) + " connus)")
        return

    if is_finished(splits):
        send_telegram(build_finish_message(splits))
    else:
        msg = build_status_message(splits, True)
        if msg:
            send_telegram(msg)

    save_file(LAST_SPLIT_FILE, current_count)
    print("OK. " + str(current_count) + " splits")


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

        splits = fetch_splits()
        if splits is None:
            send_telegram("Impossible de contacter RTRT.me")
        elif not splits:
            send_telegram("Pas encore de donnees. Course pas commencee.")
        elif is_finished(splits):
            send_telegram(build_finish_message(splits))
        else:
            msg = build_status_message(splits, False)
            if msg:
                send_telegram(msg)

        save_file(LAST_UPDATE_FILE, uid)

    print("OK " + str(len(updates)) + " msg")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "auto"
    if mode == "reply":
        mode_reply()
    else:
        mode_auto()

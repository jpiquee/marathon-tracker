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
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": message[:4000], "parse_mode": "Markdown"}
    try:
        r = requests.post(url, data=data, timeout=10)
        print(f"Telegram: {r.status_code}")
    except Exception as e:
        print(f"Erreur Telegram: {e}")


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
        print(f"API status: {r.status_code}")
        return data.get("list", [])
    except Exception as e:
        print(f"Erreur API RTRT: {e}")
        return None


def ai_analysis(splits_data, is_final=False):
    if not ANTHROPIC_API_KEY:
        return None
    try:
        headers = {
            "x-api-key": ANTHROPIC_API_KEY,
            "content-type": "application/json",
            "anthropic-version": "2023-06-01"
        }
        if is_final:
            prompt = f"""Tu es un commentateur de marathon enthousiaste.
Voici les donnees COMPLETES de Renaud au Marathon de Paris 2026.
Objectif : sub 4h (allure cible 5:41/km).
Splits : {json.dumps(splits_data, indent=2)}
Resume final en francais : objectif atteint ou non, gestion de course, felicitations. Utilise des emojis. Max 500 caracteres."""
        else:
            prompt = f"""Tu es un coach de marathon expert.
Voici les donnees EN COURS de Renaud au Marathon de Paris 2026.
Objectif : sub 4h (allure cible 5:41/km). Marathon = 42.195 km.
Splits : {json.dumps(splits_data, indent=2)}
Analyse en francais : estimation temps arrivee (tiens compte de la tendance d'allure), est-il en bonne voie pour sub 4h, conseil. Emojis. Max 400 caracteres."""

        body = {
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 400,
            "messages": [{"role": "user", "content": prompt}]
        }
        r = requests.post("https://api.anthropic.com/v1/messages", headers=headers, json=body, timeout=30)
        return r.json()["content"][0]["text"]
    except Exception as e:
        print(f"Erreur Claude API: {e}")
        return None


def build_status_message(splits, is_new_split=False):
    if not splits:
        return None

    last_split = splits[-1]
    point_name = last_split.get("pn", last_split.get("pointname", "???"))
    time_raw = last_split.get("time", "")
    dist_raw = last_split.get("dist", "0")

    if isinstance(time_raw, str) and ":" in time_raw:
        elapsed_sec = parse_time_to_seconds(time_raw)
    else:
        try:
            elapsed_sec = float(time_raw)
        except:
            elapsed_sec = 0

    try:
        dist_km = float(dist_raw)
    except:
        dist_km = 0

    remaining_km = max(0, MARATHON_DIST - dist_km)

    if dist_km > 0 and elapsed_sec > 0:
        avg_pace_sec = elapsed_sec / dist_km
        avg_pace_str = format_pace(avg_pace_sec)
    else:
        avg_pace_sec = 0
        avg_pace_str = "N/A"

    target_at_dist = dist_km * TARGET_PACE_SEC
    diff_sec = elapsed_sec - target_at_dist

    if diff_sec > 0:
        diff_str = f"🔴 Retard : +{format_time(abs(diff_sec))}"
    else:
        diff_str = f"🟢 Avance : -{format_time(abs(diff_sec))}"

    if dist_km > 0:
        estimated_finish = (elapsed_sec / dist_km) * MARATHON_DIST
        est_str = format_time(estimated_finish)
    else:
        estimated_finish = 0
        est_str = "N/A"

    progress_pct = min(100, (dist_km / MARATHON_DIST) * 100)
    bar = "█" * int(progress_pct / 10) + "░" * (10 - int(progress_pct / 10))

    header = f"🏃 *Nouveau passage : {point_name}*" if is_new_split else f"📊 *Statut Renaud — {point_name}*"

    message = (
        f"{header}\n\n"
        f"{bar} {progress_pct:.0f}%\n\n"
        f"📍 Parcouru : *{dist_km:.1f} km* / {MARATHON_DIST} km\n"
        f"📍 Restant : *{remaining_km:.1f} km*\n"
        f"⏱ Duree : *{format_time(elapsed_sec)}*\n"
        f"💨 Allure moy : *{avg_pace_str} /km*\n"
        f"{diff_str}\n"
        f"🎯 Estimation arrivee : *{est_str}*\n"
        f"(Objectif : sub 4h00)"
    )

    if diff_sec > 120:
        message += f"\n\n⚠️ *ALERTE : retard de plus de {int(diff_sec/60)} min !*"

    splits_summary = [{"point": s.get("pn", ""), "time": s.get("time", ""), "dist": s.get("dist", "")} for s in splits]
    analysis = ai_analysis(splits_summary, is_final=False)
    if analysis:
        message += f"\n\n🤖 *Analyse IA :*\n{analysis}"

    return message


def build_finish_message(splits):
    last_split = splits[-1]
    time_raw = last_split.get("time", "")
    if isinstance(time_raw, str) and ":" in time_raw:
        final_sec = parse_time_to_seconds(time_raw)
    else:
        final_sec = float(time_raw)

    sub4 = "OUI !!! 🎉🎉🎉" if final_sec < TARGET_TIME_SEC else "Non 😔"

    message = (
        f"🏁🏁🏁 *ARRIVEE DE RENAUD !!!* 🏁🏁🏁\n\n"
        f"⏱ Temps final : *{format_time(final_sec)}*\n"
        f"🎯 Sub 4h : *{sub4}*\n"
        f"💨 Allure moyenne : *{format_pace(final_sec / MARATHON_DIST)} /km*\n"
        f"📍 Distance : {MARATHON_DIST} km"
    )

    splits_summary = [{"point": s.get("pn", ""), "time": s.get("time", ""), "dist": s.get("dist", "")} for s in splits]
    analysis = ai_analysis(splits_summary, is_final=True)
    if analysis:
        message += f"\n\n🤖 *Resume IA :*\n{analysis}"

    return message


def is_finished(splits):
    if not splits:
        return False
    last = splits[-1]
    try:
        d = float(last.get("dist", "0"))
    except:
        d = 0
    pn = last.get("pn", "").lower()
    return d >= 42.0 or "finish" in pn or "arrivee" in pn or "42k" in pn


def mode_auto():
    print("=== Mode AUTO ===")
    splits = fetch_splits()

    if splits is None:
        send_telegram("⚠️ Erreur : impossible de contacter RTRT.me")
        return

    if not splits:
        last_count = int(get_file(LAST_SPLIT_FILE) or "0")
        if last_count > 0:
            send_telegram("⚠️ Aucun nouveau passage detecte !")
        else:
            print("Pas encore de donnees")
        return

    current_count = len(splits)
    last_count = int(get_file(LAST_SPLIT_FILE) or "0")

    if current_count <= last_count:
        print(f"Pas de nouveau split ({current_count} connus)")
        return

    if is_finished(splits):
        send_telegram(build_finish_message(splits))
    else:
        msg = build_status_message(splits, is_new_split=True)
        if msg:
            send_telegram(msg)

    save_file(LAST_SPLIT_FILE, current_count)
    print(f"OK. {current_count} splits ({current_count - last_count} nouveaux)")


def mode_reply():
    print("=== Mode REPLY ===")
    last_uid = get_file(LAST_UPDATE_FILE)
    last_update_id = int(last_uid) if last_uid else 0

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    try:
        r = requests.get(url, params={"offset": last_update_id + 1, "timeout": 0}, timeout=10)
        updates = r.json().get("result", [])
    except Exception as e:
        print(f"Erreur getUpdates: {e}")
        return

    if not updates:
        print("Aucun nouveau message")
        return

    for update in updates:
        update_id = update.get("update_id", 0)
        chat_id = str(update.get("message", {}).get("chat", {}).get("id", ""))

        if chat_id != TELEGRAM_CHAT_ID:
            save_file(LAST_UPDATE_FILE, update_id)
            continue

        splits = fetch_splits()
        if splits is None:
            send_telegram("⚠️ Impossible de contacter RTRT.me")
        elif not splits:
            send_telegram("⏳ Pas encore de donnees. La course n'a pas encore commence.")
        elif is_finished(splits):
            send_telegram(build_finish_message(splits))
        else:
            msg = build_status_message(splits, is_new_split=False)
            if msg:
                send_telegram(msg)

        save_file(LAST_UPDATE_FILE, update_id)

    print(f"Traite {len(updates)} message(s)")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "auto"
    if mode == "reply":
        mode_reply()
    else:
        mode_auto()

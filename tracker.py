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
TARGET_PACE_SEC = 341  # 5:41/km en secondes
TARGET_TIME_SEC = 4 * 3600  # 4h en secondes
MARATHON_DIST = 42.195  # km

API_URL = f"https://api.rtrt.me/events/{EVENT_ID}/profiles/{PROFILE_ID}/splits"
LAST_SPLIT_FILE = "last_split_count.txt"
LAST_UPDATE_FILE = "last_update_id.txt"


# === FONCTIONS UTILITAIRES ===

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
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        r = requests.post(url, data=data, timeout=10)
        print(f"Telegram: {r.status_code}")
    except Exception as e:
        print(f"Erreur Telegram: {e}")


def get_last_split_count():
    try:
        with open(LAST_SPLIT_FILE, "r") as f:
            return int(f.read().strip())
    except:
        return 0


def save_last_split_count(count):
    with open(LAST_SPLIT_FILE, "w") as f:
        f.write(str(count))


def get_last_update_id():
    try:
        with open(LAST_UPDATE_FILE, "r") as f:
            return int(f.read().strip())
    except:
        return 0


def save_last_update_id(update_id):
    with open(LAST_UPDATE_FILE, "w") as f:
        f.write(str(update_id))


def parse_time_to_seconds(time_str):
    parts = time_str.strip().split(":")
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    elif len(parts) == 2:
        return int(parts[0]) * 60 + float(parts[1])
    return 0


# === RECUPERER LES DONNEES RTRT ===

def fetch_splits():
    try:
        r = requests.get(API_URL, timeout=15)
        data = r.json()
        return data.get("list", [])
    except Exception as e:
        print(f"Erreur API RTRT: {e}")
        return None


# === ANALYSE IA AVEC CLAUDE ===

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
            prompt = f"""Tu es un commentateur de marathon enthousiaste et expert.
Voici les donnees COMPLETES de course d'un coureur au Marathon de Paris 2026.
Son objectif etait sub 4h (allure cible 5:41/km).

Donnees des splits :
{json.dumps(splits_data, indent=2)}

Fais un RESUME FINAL en francais :
- Le coureur a-t-il atteint son objectif sub 4h ?
- Comment a-t-il gere sa course (regulier, negative split, ralentissement...) ?
- Felicitations et points forts
- Utilise des emojis
Sois concis (max 600 caracteres)."""
        else:
            prompt = f"""Tu es un coach de marathon expert et bienveillant.
Voici les donnees EN COURS de course d'un coureur au Marathon de Paris 2026.
Son objectif est sub 4h (allure cible 5:41/km). Le marathon fait 42.195 km.

Donnees des splits disponibles :
{json.dumps(splits_data, indent=2)}

Analyse la course EN COURS en francais :
- Estimation du temps d'arrivee base sur l'evolution de l'allure (pas juste une moyenne, tiens compte de la tendance : accelere-t-il ou ralentit-il ?)
- Est-il en bonne voie pour le sub 4h ?
- Conseil tactique pour la suite de la course
- Utilise des emojis
Sois concis (max 500 caracteres)."""

        body = {
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 400,
            "messages": [{"role": "user", "content": prompt}]
        }
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=body,
            timeout=30
        )
        data = r.json()
        return data["content"][0]["text"]
    except Exception as e:
        print(f"Erreur Claude API: {e}")
        return None


# === CONSTRUIRE LE MESSAGE DE STATUT ===

def build_status_message(splits, is_new_split=False):
    if not splits:
        return None

    last_split = splits[-1]
    point_name = last_split.get("pn", last_split.get("pointname", "???"))
    time_raw = last_split.get("timeraw", last_split.get("time", ""))
    dist_raw = last_split.get("dist", last_split.get("distance", 0))

    # Temps ecoule
    if isinstance(time_raw, str):
        elapsed_sec = parse_time_to_seconds(time_raw)
    else:
        elapsed_sec = float(time_raw) if time_raw else 0

    # Distance
    try:
        dist_km = float(dist_raw)
    except:
        dist_km = 0

    # Km restants
    remaining_km = max(0, MARATHON_DIST - dist_km)

    # Allure moyenne
    if dist_km > 0 and elapsed_sec > 0:
        avg_pace_sec = elapsed_sec / dist_km
        avg_pace_str = format_pace(avg_pace_sec)
    else:
        avg_pace_sec = 0
        avg_pace_str = "N/A"

    # Avance / retard vs objectif
    target_at_dist = dist_km * TARGET_PACE_SEC
    diff_sec = elapsed_sec - target_at_dist

    if diff_sec > 0:
        diff_str = f"🔴 Retard : +{format_time(abs(diff_sec))}"
    else:
        diff_str = f"🟢 Avance : -{format_time(abs(diff_sec))}"

    # Estimation simple (basee sur allure moyenne)
    if dist_km > 0:
        estimated_finish = (elapsed_sec / dist_km) * MARATHON_DIST
        est_simple_str = format_time(estimated_finish)
    else:
        estimated_finish = 0
        est_simple_str = "N/A"

    # Progression en pourcentage
    progress_pct = min(100, (dist_km / MARATHON_DIST) * 100)
    progress_bar = "█" * int(progress_pct / 10) + "░" * (10 - int(progress_pct / 10))

    # Header du message
    if is_new_split:
        header = f"🏃 *Nouveau passage : {point_name}*"
    else:
        header = f"📊 *Statut actuel — {point_name}*"

    message = (
        f"{header}\n\n"
        f"{progress_bar} {progress_pct:.0f}%\n\n"
        f"📍 Parcouru : *{dist_km:.1f} km* / {MARATHON_DIST} km\n"
        f"📍 Restant : *{remaining_km:.1f} km*\n"
        f"⏱ Duree totale : *{format_time(elapsed_sec)}*\n"
        f"💨 Allure moyenne : *{avg_pace_str} /km*\n"
        f"{diff_str}\n"
        f"🎯 Estimation arrivee : *{est_simple_str}*\n"
        f"(Objectif : sub 4h00)"
    )

    # Alerte retard important
    if diff_sec > 120:
        message += f"\n\n⚠️ *ALERTE : retard de plus de {int(diff_sec/60)} minutes !*"

    # Analyse IA
    splits_summary = [{"point": s.get("pn", ""), "time": s.get("timeraw", s.get("time", "")),
                        "dist": s.get("dist", "")} for s in splits]
    analysis = ai_analysis(splits_summary, is_final=False)
    if analysis:
        message += f"\n\n🤖 *Analyse IA :*\n{analysis}"

    return message


def build_finish_message(splits):
    last_split = splits[-1]
    time_raw = last_split.get("timeraw", last_split.get("time", ""))
    if isinstance(time_raw, str):
        final_sec = parse_time_to_seconds(time_raw)
    else:
        final_sec = float(time_raw)

    sub4 = "OUI !!! 🎉🎉🎉" if final_sec < TARGET_TIME_SEC else "Non 😔"

    message = (
        f"🏁🏁🏁 *ARRIVEE !!!* 🏁🏁🏁\n\n"
        f"⏱ Temps final : *{format_time(final_sec)}*\n"
        f"🎯 Sub 4h : *{sub4}*\n"
        f"💨 Allure moyenne : *{format_pace(final_sec / MARATHON_DIST)} /km*\n"
        f"📍 Distance : {MARATHON_DIST} km"
    )

    # Resume IA final
    splits_summary = [{"point": s.get("pn", ""), "time": s.get("timeraw", s.get("time", "")),
                        "dist": s.get("dist", "")} for s in splits]
    analysis = ai_analysis(splits_summary, is_final=True)
    if analysis:
        message += f"\n\n🤖 *Resume IA :*\n{analysis}"

    return message


def is_finished(splits):
    if not splits:
        return False
    last_split = splits[-1]
    last_dist = float(last_split.get("dist", last_split.get("distance", 0)))
    last_point = last_split.get("pn", last_split.get("pointname", "")).lower()
    return (
        last_dist >= 42.0
        or "finish" in last_point
        or "arrivee" in last_point
        or "42k" in last_point
    )


# === MODE AUTOMATIQUE ===

def mode_auto():
    print("=== Mode AUTO ===")
    splits = fetch_splits()

    if splits is None:
        send_telegram("⚠️ *Erreur* : impossible de contacter RTRT.me")
        return

    if not splits:
        last_count = get_last_split_count()
        if last_count > 0:
            send_telegram(
                "⚠️ *Alerte* : Aucun nouveau passage detecte !\n"
                "Le coureur n'a pas ete vu depuis un moment."
            )
        else:
            print("Pas encore de donnees")
        return

    current_count = len(splits)
    last_count = get_last_split_count()

    if current_count <= last_count:
        print(f"Pas de nouveau split ({current_count} connus)")
        return

    # Nouveau(x) split(s) detecte(s)
    if is_finished(splits):
        send_telegram(build_finish_message(splits))
    else:
        msg = build_status_message(splits, is_new_split=True)
        if msg:
            send_telegram(msg)

    save_last_split_count(current_count)
    print(f"Termine. {current_count} splits ({current_count - last_count} nouveaux)")


# === MODE A LA DEMANDE (repondre aux messages Telegram) ===

def mode_reply():
    print("=== Mode REPLY ===")

    # Recuperer les messages non lus du bot
    last_update_id = get_last_update_id()
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    params = {"offset": last_update_id + 1, "timeout": 0}

    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
    except Exception as e:
        print(f"Erreur getUpdates: {e}")
        return

    updates = data.get("result", [])
    if not updates:
        print("Aucun nouveau message")
        return

    # Traiter chaque message
    for update in updates:
        update_id = update.get("update_id", 0)
        message = update.get("message", {})
        chat_id = str(message.get("chat", {}).get("id", ""))
        text = message.get("text", "").strip().lower()

        print(f"Message recu: '{text}' de {chat_id}")

        # Verifier que c'est bien notre utilisateur
        if chat_id != TELEGRAM_CHAT_ID:
            print(f"Chat ID inconnu: {chat_id}")
            save_last_update_id(update_id)
            continue

        # Repondre a n'importe quel message
        splits = fetch_splits()

        if splits is None:
            send_telegram("⚠️ Impossible de contacter RTRT.me pour le moment.")
        elif not splits:
            send_telegram(
                "⏳ *Pas encore de donnees*\n\n"
                "La course n'a pas encore commence, ou le coureur "
                "n'a pas encore passe de point de controle."
            )
        elif is_finished(splits):
            send_telegram(build_finish_message(splits))
        else:
            msg = build_status_message(splits, is_new_split=False)
            if msg:
                send_telegram(msg)

        save_last_update_id(update_id)

    print(f"Traite {len(updates)} message(s)")


# === POINT D'ENTREE ===

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "auto"

    if mode == "reply":
        mode_reply()
    else:
        mode_auto()

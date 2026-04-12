import requests
import os
import sys
import time
import random

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

LAST_UPDATE_FILE = "last_update_id.txt"


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


SCENARIOS = [
    ("un médecin urgentiste", "une salle d'attente bondée un lundi matin"),
    ("un plombier", "chez un client millionnaire à Monaco"),
    ("un chef étoilé", "dans un fast-food McDo"),
    ("un astronaute", "bloqué dans l'ISS avec une imprimante en panne"),
    ("un agent immobilier", "qui vend un appartement hanté"),
    ("un dentiste", "qui a peur du sang"),
    ("un professeur de yoga", "dans un embouteillage"),
    ("un pirate informatique", "qui appelle le support technique"),
    ("un détective privé", "qui enquête sur un chat disparu"),
    ("un magicien raté", "à un anniversaire d'enfants"),
    ("un traducteur simultané", "lors d'un discours politique incohérent"),
    ("un coach sportif", "qui déteste le sport"),
    ("un pilote d'avion", "qui a le vertige"),
    ("un sommelier", "dans un restaurant qui ne sert que de l'eau"),
    ("un taxidermiste", "invité à un mariage"),
    ("un juge", "au tribunal des petites créances pour un litige de 3€"),
    ("un gardien de zoo", "le jour où tous les animaux s'échappent"),
    ("un DJ", "à une soirée de retraités"),
    ("un notaire très sérieux", "qui lit un testament complètement absurde"),
    ("un pompier", "appelé pour un chat coincé... sur une fusée"),
]


def ai_funny_story():
    if not ANTHROPIC_API_KEY:
        return "Clé API manquante pour générer une histoire."
    try:
        personnage, contexte = random.choice(SCENARIOS)
        headers = {
            "x-api-key": ANTHROPIC_API_KEY,
            "content-type": "application/json",
            "anthropic-version": "2023-06-01"
        }
        prompt = (
            f"Écris une micro-histoire drôle en français avec {personnage} {contexte}. "
            f"La chute doit être inattendue et hilarante. "
            f"Max 300 caractères, emojis bienvenus. Pas d'animaux polaires."
        )
        body = {
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 350,
            "temperature": 1,
            "messages": [{"role": "user", "content": prompt}]
        }
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers, json=body, timeout=30
        )
        return r.json()["content"][0]["text"]
    except Exception as e:
        print("Erreur Claude: " + str(e))
        return "Désolé, impossible de générer une histoire pour le moment."


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

            if text.startswith("/histoire"):
                print("/histoire recu, generation en cours...")
                story = ai_funny_story()
                send_telegram(story)

    print("Listen termine")


if __name__ == "__main__":
    duration = int(sys.argv[1]) if len(sys.argv) > 1 else 3300
    mode_listen(duration)

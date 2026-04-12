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


HUMOR_STYLES = [
    "une blague absurde à chute inattendue",
    "une anecdote hilarante sur un animal",
    "un quiproquo comique entre deux personnes",
    "une histoire de malchance enchaînée façon domino",
    "une blague noire avec une fin surprenante",
    "une histoire surréaliste et loufoque",
    "une blague d'humour anglais (pince-sans-rire, ironie)",
    "une anecdote embarrassante mais drôle du quotidien",
    "une histoire avec une chute en jeu de mots",
    "un sketch comique façon Monty Python",
    "une histoire absurde inspirée des meilleures blagues scandinaves",
    "une blague de science ou de logique avec une chute inattendue",
]


def ai_funny_story():
    if not ANTHROPIC_API_KEY:
        return "Clé API manquante pour générer une histoire."
    try:
        style = random.choice(HUMOR_STYLES)
        seed = random.randint(1, 99999)
        headers = {
            "x-api-key": ANTHROPIC_API_KEY,
            "content-type": "application/json",
            "anthropic-version": "2023-06-01"
        }
        prompt = (
            f"Tu es un humoriste de niveau mondial. Raconte-moi {style}. "
            f"Elle doit être vraiment drôle, avec une chute qui surprend. "
            f"En français, max 300 caractères, avec emojis. "
            f"(variante #{seed})"
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

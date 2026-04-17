import requests
import os
import sys
import time
from datetime import datetime

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

LAST_UPDATE_FILE = "last_update_id.txt"

JOURS_FR = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]


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


def weather_icon(code):
    if code == 0:
        return "☀️"
    elif code <= 3:
        return "🌤️"
    elif code <= 48:
        return "🌫️"
    elif code <= 67:
        return "🌧️"
    elif code <= 77:
        return "❄️"
    elif code <= 82:
        return "🌦️"
    else:
        return "⛈️"


def get_weather():
    try:
        paris = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": 48.8566, "longitude": 2.3522,
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,weathercode",
                "hourly": "temperature_2m,precipitation_probability",
                "timezone": "Europe/Paris", "forecast_days": 7
            }, timeout=10
        ).json()

        bordeaux = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": 44.8378, "longitude": -0.5792,
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,weathercode",
                "timezone": "Europe/Paris", "forecast_days": 7
            }, timeout=10
        ).json()

        today = datetime.now().date()
        hourly_temps = paris["hourly"]["temperature_2m"]
        hourly_rain_prob = paris["hourly"]["precipitation_probability"]

        # Si on est ven/sam/dim, montrer lun→jeu de la semaine prochaine
        from datetime import timedelta
        weekday = today.weekday()
        if weekday <= 3:
            start_paris = today
        else:
            start_paris = today + timedelta(days=7 - weekday)

        # --- PARIS : matin moto ---
        lines = ["🏍️ PARIS — matin 7h-9h (moto)"]
        for i, date_str in enumerate(paris["daily"]["time"]):
            d = datetime.strptime(date_str, "%Y-%m-%d").date()
            if d < start_paris:
                continue
            if d.weekday() > 3:  # Stop après jeudi
                break

            jour_label = JOURS_FR[d.weekday()] + " " + d.strftime("%d/%m")
            t7 = hourly_temps[i * 24 + 7]
            t8 = hourly_temps[i * 24 + 8]
            t9 = hourly_temps[i * 24 + 9]
            matin = round((t7 + t8 + t9) / 3)
            pluie_prob = max(
                hourly_rain_prob[i * 24 + 7],
                hourly_rain_prob[i * 24 + 8],
                hourly_rain_prob[i * 24 + 9]
            )
            code = paris["daily"]["weathercode"][i]
            icon = weather_icon(code)
            warn = ""
            if matin < 5:
                warn = " ❄️ FROID"
            elif matin < 10:
                warn = " 🥶 frais"
            pluie_str = (" 🌧️ pluie " + str(pluie_prob) + "%") if pluie_prob >= 40 else ""
            lines.append(jour_label + " : " + str(matin) + "°C " + icon + warn + pluie_str)

        # --- BORDEAUX : vendredi→dimanche ---
        lines.append("")
        lines.append("🌿 BORDEAUX — ven→dim (jardin & sport)")
        found_weekend = False
        for i, date_str in enumerate(bordeaux["daily"]["time"]):
            d = datetime.strptime(date_str, "%Y-%m-%d").date()
            if d < today:
                continue
            if d.weekday() not in (4, 5, 6):  # Ven, Sam, Dim uniquement
                continue
            found_weekend = True
            jour_label = JOURS_FR[d.weekday()] + " " + d.strftime("%d/%m")
            tmax = round(bordeaux["daily"]["temperature_2m_max"][i])
            tmin = round(bordeaux["daily"]["temperature_2m_min"][i])
            pluie = bordeaux["daily"]["precipitation_sum"][i]
            code = bordeaux["daily"]["weathercode"][i]
            icon = weather_icon(code)
            if pluie < 2:
                verdict = "✅ top"
            elif pluie < 8:
                verdict = "⚠️ mitigé"
            else:
                verdict = "❌ pluie"
            lines.append(
                jour_label + " : " + str(tmax) + "°/" + str(tmin) + "° " +
                icon + " " + str(round(pluie, 1)) + "mm " + verdict
            )
        if not found_weekend:
            lines.append("Pas de week-end dans les 7 prochains jours.")

        return "\n".join(lines)

    except Exception as e:
        print("Erreur météo: " + str(e))
        return "Désolé, météo indisponible pour le moment."


def ai_funny_story():
    if not ANTHROPIC_API_KEY:
        return "Clé API manquante pour générer une histoire."
    try:
        headers = {
            "x-api-key": ANTHROPIC_API_KEY,
            "content-type": "application/json",
            "anthropic-version": "2023-06-01"
        }
        prompt = (
            "Tu es Laurent Baffie. Balance une de tes vacheries ou blagues cultes, "
            "style best of Baffie : courte, percutante, politiquement incorrecte, "
            "cash et sans filtre, chute assassine. "
            "Public adulte. En français. Maximum 400 caractères."
        )
        body = {
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 400,
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
            elif text.startswith("/meteo"):
                print("/meteo recu, recuperation en cours...")
                meteo = get_weather()
                send_telegram(meteo)

    print("Listen termine")


if __name__ == "__main__":
    duration = int(sys.argv[1]) if len(sys.argv) > 1 else 3300
    mode_listen(duration)

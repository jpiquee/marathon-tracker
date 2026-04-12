import requests
import json
import os
import sys

# === CONFIGURATION ===

TELEGRAM_BOT_TOKEN = os.environ.get(“TELEGRAM_BOT_TOKEN”, “”)
TELEGRAM_CHAT_ID = os.environ.get(“TELEGRAM_CHAT_ID”, “”)
ANTHROPIC_API_KEY = os.environ.get(“ANTHROPIC_API_KEY”, “”)

EVENT_ID = “ASO-PARISMARATHON-2026”
PROFILE_ID = “RN4LKWXU”
TARGET_PACE_SEC = 341  # 5:41/km en secondes
TARGET_TIME_SEC = 4 * 3600  # 4h en secondes
MARATHON_DIST = 42.195  # km

API_URL = f”https://api.rtrt.me/events/{EVENT_ID}/profiles/{PROFILE_ID}/splits”
LAST_SPLIT_FILE = “last_split_count.txt”

# === FONCTIONS UTILITAIRES ===

def format_time(seconds):
“”“Convertit des secondes en format H:MM:SS”””
h = int(seconds // 3600)
m = int((seconds % 3600) // 60)
s = int(seconds % 60)
return f”{h}:{m:02d}:{s:02d}”

def format_pace(seconds_per_km):
“”“Convertit des secondes/km en format M:SS”””
m = int(seconds_per_km // 60)
s = int(seconds_per_km % 60)
return f”{m}:{s:02d}”

def send_telegram(message):
“”“Envoie un message via Telegram”””
url = f”https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage”
data = {
“chat_id”: TELEGRAM_CHAT_ID,
“text”: message,
“parse_mode”: “Markdown”
}
try:
r = requests.post(url, data=data, timeout=10)
print(f”Telegram: {r.status_code}”)
except Exception as e:
print(f”Erreur Telegram: {e}”)

def get_last_split_count():
“”“Lit le nombre de splits deja vus”””
try:
with open(LAST_SPLIT_FILE, “r”) as f:
return int(f.read().strip())
except:
return 0

def save_last_split_count(count):
“”“Sauvegarde le nombre de splits”””
with open(LAST_SPLIT_FILE, “w”) as f:
f.write(str(count))

def parse_time_to_seconds(time_str):
“”“Convertit un temps HH:MM:SS ou H:MM:SS en secondes”””
parts = time_str.strip().split(”:”)
if len(parts) == 3:
return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
elif len(parts) == 2:
return int(parts[0]) * 60 + float(parts[1])
return 0

def generate_summary(splits_data):
“”“Genere un resume final avec Claude API”””
if not ANTHROPIC_API_KEY:
return None
try:
headers = {
“x-api-key”: ANTHROPIC_API_KEY,
“content-type”: “application/json”,
“anthropic-version”: “2023-06-01”
}
prompt = f””“Tu es un commentateur de marathon enthousiaste.
Voici les donnees de course d’un coureur au Marathon de Paris 2026.
Son objectif etait sub 4h (allure 5:41/km).

Donnees des splits :
{json.dumps(splits_data, indent=2)}

Fais un resume final de la course en francais, avec :

- Temps final et objectif atteint ou non
- Points forts et moments cles
- Felicitations ou encouragements
- Utilise des emojis
  Sois concis (max 500 caracteres).”””
  
  ```
    body = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 300,
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
  ```
  
  except Exception as e:
  print(f”Erreur Claude API: {e}”)
  return None

# === LOGIQUE PRINCIPALE ===

def main():
print(”=== Marathon Tracker ===”)

```
# 1. Recuperer les donnees RTRT
try:
    r = requests.get(API_URL, timeout=15)
    data = r.json()
    print(f"API status: {r.status_code}")
except Exception as e:
    print(f"Erreur API: {e}")
    send_telegram("⚠️ *Erreur* : impossible de contacter RTRT.me")
    return

# 2. Verifier s'il y a des donnees
splits = data.get("list", [])

if not splits:
    error_type = data.get("error", {}).get("type", "")
    if error_type == "no_results":
        print("Pas encore de donnees")
        # Verifier si ca fait longtemps
        last_count = get_last_split_count()
        if last_count > 0:
            send_telegram(
                "⚠️ *Alerte* : Aucun nouveau passage detecte !\n"
                "Le coureur n'a pas ete vu depuis un moment."
            )
    else:
        print("Course pas encore commencee ou coureur non trouve")
    return

# 3. Comparer avec les donnees precedentes
current_count = len(splits)
last_count = get_last_split_count()

if current_count <= last_count:
    print(f"Pas de nouveau split ({current_count} splits connus)")
    # Envoyer une alerte si meme nombre depuis longtemps
    if last_count > 0 and current_count == last_count:
        print("Meme nombre de splits - pas de notification")
    return

# 4. Traiter les nouveaux splits
new_splits = splits[last_count:]

for split in new_splits:
    # Extraire les infos du split
    point_name = split.get("pn", split.get("pointname", "???"))
    time_raw = split.get("timeraw", split.get("time", ""))
    dist_raw = split.get("dist", split.get("distance", 0))

    # Convertir le temps en secondes
    if isinstance(time_raw, str):
        elapsed_sec = parse_time_to_seconds(time_raw)
    else:
        elapsed_sec = float(time_raw) if time_raw else 0

    # Distance en km
    try:
        dist_km = float(dist_raw)
    except:
        dist_km = 0

    # Calculer l'allure
    if dist_km > 0 and elapsed_sec > 0:
        pace_sec = elapsed_sec / dist_km
        pace_str = format_pace(pace_sec)
    else:
        pace_sec = 0
        pace_str = "N/A"

    # Temps cible pour cette distance
    target_at_dist = dist_km * TARGET_PACE_SEC
    diff_sec = elapsed_sec - target_at_dist

    # Construire le message
    if diff_sec > 0:
        diff_str = f"🔴 Retard : +{format_time(abs(diff_sec))}"
    else:
        diff_str = f"🟢 Avance : -{format_time(abs(diff_sec))}"

    # Estimation temps final
    if dist_km > 0:
        estimated_finish = (elapsed_sec / dist_km) * MARATHON_DIST
        est_str = format_time(estimated_finish)
    else:
        est_str = "N/A"

    message = (
        f"🏃 *Passage : {point_name}*\n"
        f"📍 Distance : {dist_km:.1f} km\n"
        f"⏱ Temps : {format_time(elapsed_sec)}\n"
        f"💨 Allure : {pace_str} /km\n"
        f"{diff_str}\n"
        f"🎯 Estimation arrivee : {est_str}\n"
        f"(Objectif : sub 4h00)"
    )

    # Alerte retard important (> 2 min)
    if diff_sec > 120:
        message += f"\n\n⚠️ *ALERTE : retard de plus de 2 minutes !*"

    send_telegram(message)

# 5. Verifier si le coureur a termine
last_split = splits[-1]
last_dist = float(last_split.get("dist", last_split.get("distance", 0)))
last_point = last_split.get("pn", last_split.get("pointname", "")).lower()

is_finish = (
    last_dist >= 42.0
    or "finish" in last_point
    or "arrivee" in last_point
    or "42k" in last_point
    or "42.195" in str(last_dist)
)

if is_finish and current_count > last_count:
    # Temps final
    time_raw = last_split.get("timeraw", last_split.get("time", ""))
    if isinstance(time_raw, str):
        final_sec = parse_time_to_seconds(time_raw)
    else:
        final_sec = float(time_raw)

    sub4 = "OUI !!!" if final_sec < TARGET_TIME_SEC else "Non"

    finish_msg = (
        f"🏁🏁🏁 *ARRIVEE !!!* 🏁🏁🏁\n\n"
        f"⏱ Temps final : *{format_time(final_sec)}*\n"
        f"🎯 Sub 4h : *{sub4}*\n"
        f"💨 Allure moyenne : {format_pace(final_sec / MARATHON_DIST)} /km"
    )

    # Resume IA si disponible
    summary = generate_summary(
        [{"point": s.get("pn", ""), "time": s.get("time", ""),
          "dist": s.get("dist", "")} for s in splits]
    )
    if summary:
        finish_msg += f"\n\n📝 *Resume IA :*\n{summary}"

    send_telegram(finish_msg)

# 6. Sauvegarder l'etat
save_last_split_count(current_count)
print(f"Termine. {current_count} splits ({current_count - last_count} nouveaux)")
```

if **name** == “**main**”:
main()

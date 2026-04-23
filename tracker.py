import requests
import os
import sys
import time
import json
import re
from datetime import datetime

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
LAST_UPDATE_FILE = "last_update_id.txt"

try:
    from gmail_organizer import (
        get_gmail_service, load_rules, save_rules, commit_rules_to_github,
        load_pending, save_pending, fetch_unread_emails,
        apply_rules_to_unread, suggest_label, classify_with_ai,
        audit_classify_with_ai, apply_label_to_email, learn_rule, LABELS_DEFAULT,
        reset_gmail_labels
    )
    GMAIL_AVAILABLE = True
except ImportError:
    GMAIL_AVAILABLE = False

JOURS_FR = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]


def send_telegram(message):
    url = "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/sendMessage"
    try:
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message[:4000]}, timeout=10)
    except Exception as e:
        print("Erreur Telegram: " + str(e))


def send_telegram_with_buttons(message, buttons):
    url = "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/sendMessage"
    try:
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message[:4000], "reply_markup": {"inline_keyboard": buttons}}, timeout=10)
    except Exception as e:
        print("Erreur Telegram buttons: " + str(e))


def answer_callback_query(cq_id, text=""):
    try:
        requests.post("https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/answerCallbackQuery",
                      json={"callback_query_id": cq_id, "text": text}, timeout=5)
    except Exception:
        pass


def edit_message_text(chat_id, message_id, text):
    try:
        requests.post("https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/editMessageText",
                      json={"chat_id": chat_id, "message_id": message_id, "text": text[:4000]}, timeout=10)
    except Exception:
        pass


def get_file(name):
    try:
        with open(name, "r") as f:
            return f.read().strip()
    except Exception:
        return ""


def save_file(name, value):
    with open(name, "w") as f:
        f.write(str(value))


def weather_icon(code):
    if code == 0: return "☀️"
    elif code <= 3: return "🌤️"
    elif code <= 48: return "🌫️"
    elif code <= 67: return "🌧️"
    elif code <= 77: return "❄️"
    elif code <= 82: return "🌦️"
    else: return "⛈️"


def get_weather():
    try:
        paris = requests.get("https://api.open-meteo.com/v1/forecast", params={"latitude": 48.8566, "longitude": 2.3522, "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,weathercode", "hourly": "temperature_2m,precipitation_probability", "timezone": "Europe/Paris", "forecast_days": 7}, timeout=10).json()
        bordeaux = requests.get("https://api.open-meteo.com/v1/forecast", params={"latitude": 44.8378, "longitude": -0.5792, "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,weathercode", "timezone": "Europe/Paris", "forecast_days": 7}, timeout=10).json()
        biarritz = requests.get("https://api.open-meteo.com/v1/forecast", params={"latitude": 43.4833, "longitude": -1.5586, "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,weathercode", "timezone": "Europe/Paris", "forecast_days": 7}, timeout=10).json()
        today = datetime.now().date()
        from datetime import timedelta
        hourly_temps = paris["hourly"]["temperature_2m"]
        hourly_rain_prob = paris["hourly"]["precipitation_probability"]
        weekday = today.weekday()
        start_paris = today if weekday <= 3 else today + timedelta(days=7 - weekday)
        lines = ["🏍️ PARIS — matin 7h-9h (moto)"]
        for i, date_str in enumerate(paris["daily"]["time"]):
            d = datetime.strptime(date_str, "%Y-%m-%d").date()
            if d < start_paris: continue
            if d.weekday() > 3: break
            matin = round((hourly_temps[i*24+7] + hourly_temps[i*24+8] + hourly_temps[i*24+9]) / 3)
            pluie_prob = max(hourly_rain_prob[i*24+7], hourly_rain_prob[i*24+8], hourly_rain_prob[i*24+9])
            warn = " ❄️ FROID" if matin < 5 else (" 🥶 frais" if matin < 10 else "")
            pluie_str = (" 🌧️ pluie " + str(pluie_prob) + "%") if pluie_prob >= 40 else ""
            lines.append(JOURS_FR[d.weekday()] + " " + d.strftime("%d/%m") + " : " + str(matin) + "°C " + weather_icon(paris["daily"]["weathercode"][i]) + warn + pluie_str)
        lines.append("")
        lines.append("🌿 BORDEAUX — ven→dim (jardin & sport)")
        found = False
        for i, date_str in enumerate(bordeaux["daily"]["time"]):
            d = datetime.strptime(date_str, "%Y-%m-%d").date()
            if d < today or d.weekday() not in (4, 5, 6): continue
            found = True
            pluie = bordeaux["daily"]["precipitation_sum"][i]
            verdict = "✅ top" if pluie < 2 else ("⚠️ mitigé" if pluie < 8 else "❌ pluie")
            lines.append(JOURS_FR[d.weekday()] + " " + d.strftime("%d/%m") + " : " + str(round(bordeaux["daily"]["temperature_2m_max"][i])) + "°/" + str(round(bordeaux["daily"]["temperature_2m_min"][i])) + "° " + weather_icon(bordeaux["daily"]["weathercode"][i]) + " " + str(round(pluie, 1)) + "mm " + verdict)
        if not found: lines.append("Pas de week-end dans les 7 prochains jours.")
        lines.append("")
        lines.append("🏄 BIARRITZ — sam & dim")
        found = False
        for i, date_str in enumerate(biarritz["daily"]["time"]):
            d = datetime.strptime(date_str, "%Y-%m-%d").date()
            if d < today or d.weekday() not in (5, 6): continue
            found = True
            pluie = biarritz["daily"]["precipitation_sum"][i]
            verdict = "✅ top" if pluie < 2 else ("⚠️ mitigé" if pluie < 8 else "❌ pluie")
            lines.append(JOURS_FR[d.weekday()] + " " + d.strftime("%d/%m") + " : " + str(round(biarritz["daily"]["temperature_2m_max"][i])) + "°/" + str(round(biarritz["daily"]["temperature_2m_min"][i])) + "° " + weather_icon(biarritz["daily"]["weathercode"][i]) + " " + str(round(pluie, 1)) + "mm " + verdict)
        if not found: lines.append("Pas de sam/dim dans les 7 prochains jours.")
        return "\n".join(lines)
    except Exception:
        return "Meteo indisponible."


def get_weather_bordeaux_15():
    try:
        data = requests.get("https://api.open-meteo.com/v1/forecast", params={"latitude": 44.8378, "longitude": -0.5792, "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,weathercode", "timezone": "Europe/Paris", "forecast_days": 15}, timeout=10).json()
        today = datetime.now().date()
        lines = ["🌿 BORDEAUX — 15 jours"]
        for i, date_str in enumerate(data["daily"]["time"]):
            d = datetime.strptime(date_str, "%Y-%m-%d").date()
            if d < today: continue
            pluie = data["daily"]["precipitation_sum"][i]
            verdict = "✅ top" if pluie < 2 else ("⚠️ mitigé" if pluie < 8 else "❌ pluie")
            lines.append(JOURS_FR[d.weekday()] + " " + d.strftime("%d/%m") + " : " + str(round(data["daily"]["temperature_2m_max"][i])) + "°/" + str(round(data["daily"]["temperature_2m_min"][i])) + "° " + weather_icon(data["daily"]["weathercode"][i]) + " " + str(round(pluie, 1)) + "mm " + verdict)
        return "\n".join(lines)
    except Exception:
        return "Meteo15 indisponible."


def ai_funny_story():
    if not ANTHROPIC_API_KEY:
        return "Cle API manquante."
    try:
        r = requests.post("https://api.anthropic.com/v1/messages",
            headers={"x-api-key": ANTHROPIC_API_KEY, "content-type": "application/json", "anthropic-version": "2023-06-01"},
            json={"model": "claude-sonnet-4-20250514", "max_tokens": 400, "temperature": 1,
                  "messages": [{"role": "user", "content": "Tu es Laurent Baffie. Balance une vacherie culte, courte, percutante, politiquement incorrecte, chute assassine. Public adulte. En francais. Max 400 caracteres."}]},
            timeout=30)
        return r.json()["content"][0]["text"]
    except Exception:
        return "Impossible de generer une histoire."


def _gmail_check():
    if not GMAIL_AVAILABLE:
        send_telegram("Module Gmail non disponible.")
        return None
    service = get_gmail_service()
    if not service:
        send_telegram("Connexion Gmail impossible. Verifiez GMAIL_TOKEN.")
    return service


def handle_ranger_mails():
    service = _gmail_check()
    if not service:
        return
    send_telegram("📬 Recuperation des emails non-lus...")
    emails = fetch_unread_emails(service, max_results=8)
    if not emails:
        send_telegram("✅ Aucun email non-lu !")
        return
    rules = load_rules()
    pending = load_pending()
    send_telegram(f"📧 {len(emails)} email(s) a classer :")
    for email in emails:
        label = suggest_label(email, rules)
        source = "regle apprise" if label else "IA"
        if not label:
            label = classify_with_ai(email, rules, ANTHROPIC_API_KEY)
        pending[email["id"]] = {"subject": email["subject"], "sender": email["sender"], "snippet": email["snippet"], "suggested_label": label}
        text = f"De: {email['sender'][:55]}\nObjet: {email['subject'][:65]}\n{email['snippet'][:100]}\n\nSuggestion ({source}): [ {label} ]"
        buttons = [[{"text": "✅ OK", "callback_data": f"gmail_ok:{email['id']}:{label}"}, {"text": "✏️ Modifier", "callback_data": f"gmail_change:{email['id']}"}, {"text": "⏭️ Ignorer", "callback_data": f"gmail_skip:{email['id']}"}]]
        send_telegram_with_buttons(text, buttons)
    save_pending(pending)


def handle_audit_mails():
    service = _gmail_check()
    if not service:
        return
    send_telegram("🔍 Analyse des emails non-lus en cours...")
    emails = fetch_unread_emails(service, max_results=50)
    if not emails:
        send_telegram("✅ Aucun email non-lu !")
        return
    rules = load_rules()
    send_telegram(f"📊 {len(emails)} emails non-lus analyses par IA...")
    classifiables = []
    personal_count = 0
    for email in emails:
        label = suggest_label(email, rules)
        if label:
            classifiables.append((email, label))
        else:
            label = audit_classify_with_ai(email, rules, ANTHROPIC_API_KEY)
            if label:
                classifiables.append((email, label))
            else:
                personal_count += 1
    if personal_count:
        send_telegram(f"👤 {personal_count} email(s) personnel(s) ou action requise ignores (restent non-lus).")
    if not classifiables:
        send_telegram("✅ Tous vos emails non-lus necessitent votre attention. Rien a classer automatiquement.")
        return
    groups = {}
    for email, label in classifiables:
        m = re.search(r"@([\w.\-]+)", email["sender"])
        domain = "@" + m.group(1) if m else "inconnu"
        if domain not in groups:
            groups[domain] = {"emails": [], "label": label}
        groups[domain]["emails"].append(email)
    pending = load_pending()
    shown = 0
    send_telegram(f"📁 {len(classifiables)} emails classifiables en {len(groups)} groupe(s) :")
    for i, (domain, data) in enumerate(sorted(groups.items(), key=lambda x: -len(x[1]["emails"]))):
        if shown >= 20:
            send_telegram(f"(+{len(groups)-shown} autres groupes — relancez /audit_mails)")
            break
        label = data["label"]
        grp_emails = data["emails"]
        gid = f"ag{i}"
        pending[gid] = {"type": "audit", "domain": domain, "email_ids": [e["id"] for e in grp_emails], "suggested_label": label, "count": len(grp_emails), "sample_subject": grp_emails[0]["subject"]}
        text = f"📨 {domain} ({len(grp_emails)} email(s))\nEx: {grp_emails[0]['subject'][:60]}\n\nSuggestion: [ {label} ]"
        buttons = [[{"text": f"✅ OK ({len(grp_emails)})", "callback_data": f"audit_ok:{gid}:{label}"}, {"text": "✏️ Modifier", "callback_data": f"audit_chg:{gid}"}, {"text": "⏭️ Ignorer", "callback_data": f"audit_skp:{gid}"}]]
        send_telegram_with_buttons(text, buttons)
        shown += 1
    save_pending(pending)


def handle_appliquer_regles():
    service = _gmail_check()
    if not service:
        return
    rules = load_rules()
    if not rules:
        send_telegram("📋 Aucune regle apprise. Utilisez /ranger_mails ou /audit_mails d'abord.")
        return
    send_telegram(f"⚙️ Application de {len(rules)} regles sur tous les emails non-lus...")
    counts, skipped_personal, skipped_no_rule = apply_rules_to_unread(service, rules)
    if not counts and skipped_personal == 0 and skipped_no_rule == 0:
        send_telegram("✅ Aucun email non-lu a traiter.")
        return
    lines = ["✅ Regles appliquees :"]
    for label, count in sorted(counts.items(), key=lambda x: -x[1]):
        lines.append(f"  • {label}: {count} email(s)")
    if skipped_personal:
        lines.append(f"  👤 Proteges (personnels/conversations): {skipped_personal} email(s)")
    if skipped_no_rule:
        lines.append(f"  ❓ Sans regle connue: {skipped_no_rule} email(s) (utilisez /ranger_mails)")
    send_telegram("\n".join(lines))


def handle_gmail_callback(callback_query):
    cq_id = callback_query.get("id", "")
    data = callback_query.get("data", "")
    chat_id = str(callback_query.get("message", {}).get("chat", {}).get("id", ""))
    message_id = callback_query.get("message", {}).get("message_id")
    if chat_id != TELEGRAM_CHAT_ID:
        return
    if not GMAIL_AVAILABLE:
        answer_callback_query(cq_id, "Module Gmail non disponible")
        return
    parts = data.split(":", 2)
    action = parts[0] if parts else ""
    key = parts[1] if len(parts) > 1 else ""
    label = parts[2] if len(parts) > 2 else ""
    pending = load_pending()
    rules = load_rules()
    info = pending.get(key, {})
    if action in ("gmail_ok", "gmail_lbl"):
        service = get_gmail_service()
        if service and key:
            ok = apply_label_to_email(service, key, label)
            if ok:
                answer_callback_query(cq_id, f"✅ Classe dans {label}")
                edit_message_text(chat_id, message_id, f"✅ {info.get('subject', key)[:60]}\n→ {label}")
                if info:
                    updated = learn_rule(info, label, rules)
                    save_rules(updated)
                    commit_rules_to_github(updated)
            else:
                answer_callback_query(cq_id, "❌ Erreur")
        pending.pop(key, None)
        save_pending(pending)
    elif action == "gmail_change":
        rows = []
        row = []
        for lbl in LABELS_DEFAULT:
            row.append({"text": lbl, "callback_data": f"gmail_lbl:{key}:{lbl}"})
            if len(row) == 2:
                rows.append(row)
                row = []
        if row: rows.append(row)
        send_telegram_with_buttons(f"Dossier pour:\n{info.get('subject', key)[:60]}", rows)
        answer_callback_query(cq_id)
    elif action == "gmail_skip":
        answer_callback_query(cq_id, "⏭️ Ignore")
        edit_message_text(chat_id, message_id, f"⏭️ Ignore: {info.get('subject', key)[:60]}")
        pending.pop(key, None)
        save_pending(pending)


def handle_audit_callback(callback_query):
    cq_id = callback_query.get("id", "")
    data = callback_query.get("data", "")
    chat_id = str(callback_query.get("message", {}).get("chat", {}).get("id", ""))
    message_id = callback_query.get("message", {}).get("message_id")
    if chat_id != TELEGRAM_CHAT_ID:
        return
    parts = data.split(":", 2)
    action = parts[0] if parts else ""
    gid = parts[1] if len(parts) > 1 else ""
    label = parts[2] if len(parts) > 2 else ""
    pending = load_pending()
    rules = load_rules()
    group = pending.get(gid, {})
    domain = group.get("domain", "")
    email_ids = group.get("email_ids", [])
    count = group.get("count", 0)
    if action in ("audit_ok", "audit_lbl"):
        service = get_gmail_service()
        if service and email_ids:
            success = sum(1 for eid in email_ids if apply_label_to_email(service, eid, label))
            answer_callback_query(cq_id, f"✅ {success}/{count} classes dans {label}")
            edit_message_text(chat_id, message_id, f"✅ {domain} ({success} emails)\n→ {label}")
            if domain:
                rules[domain] = label
                save_rules(rules)
                commit_rules_to_github(rules)
        pending.pop(gid, None)
        save_pending(pending)
    elif action == "audit_chg":
        rows = []
        row = []
        for lbl in LABELS_DEFAULT:
            row.append({"text": lbl, "callback_data": f"audit_lbl:{gid}:{lbl}"})
            if len(row) == 2:
                rows.append(row)
                row = []
        if row: rows.append(row)
        send_telegram_with_buttons(f"Dossier pour {domain} ({count} emails) :", rows)
        answer_callback_query(cq_id)
    elif action == "audit_skp":
        answer_callback_query(cq_id, "⏭️ Ignore")
        edit_message_text(chat_id, message_id, f"⏭️ Ignore: {domain}")
        pending.pop(gid, None)
        save_pending(pending)


def handle_reset_gmail():
    if not GMAIL_AVAILABLE:
        send_telegram("Module Gmail non disponible.")
        return
    buttons = [[
        {"text": "✅ Confirmer le reset", "callback_data": "reset_confirm"},
        {"text": "❌ Annuler", "callback_data": "reset_cancel"}
    ]]
    send_telegram_with_buttons(
        "⚠️ RESET GMAIL\n\nCela va :\n• Retirer tous les labels du bot\n• Remettre tous ces emails en non-lu\n\nConfirmer ?",
        buttons
    )


def handle_reset_callback(callback_query):
    cq_id = callback_query.get("id", "")
    data = callback_query.get("data", "")
    chat_id = str(callback_query.get("message", {}).get("chat", {}).get("id", ""))
    message_id = callback_query.get("message", {}).get("message_id")
    if chat_id != TELEGRAM_CHAT_ID:
        return
    if data == "reset_confirm":
        answer_callback_query(cq_id, "⏳ Reset en cours...")
        edit_message_text(chat_id, message_id, "⏳ Reset Gmail en cours...")
        service = get_gmail_service()
        if not service:
            send_telegram("Connexion Gmail impossible.")
            return
        def on_progress(n):
            edit_message_text(chat_id, message_id, f"⏳ {n} emails trouvés, nettoyage en cours...")

        count = reset_gmail_labels(service, on_progress=on_progress)
        if count < 0:
            edit_message_text(chat_id, message_id, "❌ Erreur lors du reset Gmail.")
        elif count == 0:
            edit_message_text(chat_id, message_id, "✅ Aucun email à réinitialiser.")
        else:
            edit_message_text(chat_id, message_id, f"✅ Reset terminé : {count} email(s) remis en non-lu, labels retirés.")
    elif data == "reset_cancel":
        answer_callback_query(cq_id, "Annulé")
        edit_message_text(chat_id, message_id, "❌ Reset annulé.")


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
            r = requests.get(url, params={"offset": last_update_id + 1, "timeout": poll_timeout}, timeout=poll_timeout + 5)
            updates = r.json().get("result", [])
        except Exception as e:
            print("Erreur polling: " + str(e))
            time.sleep(5)
            continue
        for update in updates:
            uid = update.get("update_id", 0)
            last_update_id = uid
            save_file(LAST_UPDATE_FILE, uid)
            cq = update.get("callback_query", {})
            if cq:
                cb = cq.get("data", "")
                if cb.startswith("gmail_"):
                    handle_gmail_callback(cq)
                elif cb.startswith("audit_"):
                    handle_audit_callback(cq)
                elif cb.startswith("reset_"):
                    handle_reset_callback(cq)
                continue
            message = update.get("message", {})
            cid = str(message.get("chat", {}).get("id", ""))
            text = message.get("text", "").strip()
            if cid != TELEGRAM_CHAT_ID:
                continue
            if text.startswith("/reset_gmail"):
                handle_reset_gmail()
            elif text.startswith("/audit_mails"):
                handle_audit_mails()
            elif text.startswith("/appliquer_regles"):
                handle_appliquer_regles()
            elif text.startswith("/ranger_mails"):
                handle_ranger_mails()
            elif text.startswith("/histoire"):
                send_telegram(ai_funny_story())
            elif text.startswith("/meteo15"):
                send_telegram(get_weather_bordeaux_15())
            elif text.startswith("/meteo"):
                send_telegram(get_weather())
    print("Listen termine")


if __name__ == "__main__":
    duration = int(sys.argv[1]) if len(sys.argv) > 1 else 3300
    mode_listen(duration)

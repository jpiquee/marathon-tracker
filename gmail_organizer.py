import os
import json
import re
import base64
import requests

GMAIL_RULES_FILE = "gmail_rules.json"
PENDING_EMAILS_FILE = "pending_emails.json"

LABELS_DEFAULT = [
    "Travail", "Personnel", "Newsletter", "Commande",
    "Finance", "Voyage", "Social", "Securite", "Autre"
]

# Labels jamais appliques automatiquement : l'email reste en inbox non-lu
LABELS_NO_AUTO = {"Securite"}

# Domaines personnels / generiques : jamais de regle domaine seul
PERSONAL_DOMAINS = {
    "gmail.com", "yahoo.fr", "yahoo.com", "outlook.com", "hotmail.com",
    "hotmail.fr", "orange.fr", "free.fr", "laposte.net", "sfr.fr",
    "wanadoo.fr", "icloud.com", "me.com", "google.com", "live.fr", "live.com"
}

# Prefixes de reponse/transfert = email de conversation, ne pas toucher
REPLY_PREFIXES = ("re:", "re :", "ref:", "fwd:", "fw:", "tr:", "tr :")


def get_gmail_service():
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
        token_path = "token.json"
        if not os.path.exists(token_path):
            token_json = os.environ.get("GMAIL_TOKEN", "")
            if not token_json:
                print("GMAIL_TOKEN manquant")
                return None
            with open(token_path, "w") as f:
                f.write(token_json)
        creds = Credentials.from_authorized_user_file(token_path)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(token_path, "w") as f:
                f.write(creds.to_json())
        return build("gmail", "v1", credentials=creds)
    except Exception as e:
        print("Erreur Gmail: " + str(e))
        return None


def load_rules():
    try:
        with open(GMAIL_RULES_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def save_rules(rules):
    with open(GMAIL_RULES_FILE, "w") as f:
        json.dump(rules, f, ensure_ascii=False, indent=2)


def commit_rules_to_github(rules):
    token = os.environ.get("GITHUB_TOKEN", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "jpiquee/marathon-tracker")
    if not token:
        return
    content_b64 = base64.b64encode(json.dumps(rules, ensure_ascii=False, indent=2).encode()).decode()
    api_url = f"https://api.github.com/repos/{repo}/contents/gmail_rules.json"
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}
    sha = None
    r = requests.get(api_url, headers=headers, timeout=10)
    if r.status_code == 200:
        sha = r.json().get("sha")
    body = {"message": f"chore: apprentissage Gmail ({len(rules)} regles) [skip ci]", "content": content_b64, "branch": "main"}
    if sha:
        body["sha"] = sha
    requests.put(api_url, headers=headers, json=body, timeout=15)


def load_pending():
    try:
        with open(PENDING_EMAILS_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def save_pending(pending):
    with open(PENDING_EMAILS_FILE, "w") as f:
        json.dump(pending, f, ensure_ascii=False, indent=2)


def _get_email_meta(service, msg_id):
    data = service.users().messages().get(
        userId="me", id=msg_id, format="metadata",
        metadataHeaders=["Subject", "From"]
    ).execute()
    headers = {h["name"]: h["value"] for h in data["payload"]["headers"]}
    return {
        "id": msg_id,
        "subject": headers.get("Subject", "(sans objet)")[:100],
        "sender": headers.get("From", "inconnu")[:80],
        "snippet": data.get("snippet", "")[:150],
    }


def fetch_unread_emails(service, max_results=8):
    try:
        result = service.users().messages().list(
            userId="me", q="is:unread in:inbox", maxResults=max_results
        ).execute()
        return [_get_email_meta(service, m["id"]) for m in result.get("messages", [])]
    except Exception as e:
        print("Erreur fetch unread: " + str(e))
        return []


def fetch_all_unread_emails(service):
    """Recupere TOUS les emails non-lus via pagination."""
    try:
        all_msgs = []
        params = {"userId": "me", "q": "is:unread in:inbox", "maxResults": 500}
        result = service.users().messages().list(**params).execute()
        all_msgs.extend(result.get("messages", []))
        while "nextPageToken" in result:
            result = service.users().messages().list(
                **params, pageToken=result["nextPageToken"]
            ).execute()
            all_msgs.extend(result.get("messages", []))
        print(f"Total non-lus trouves: {len(all_msgs)}")
        return [_get_email_meta(service, m["id"]) for m in all_msgs]
    except Exception as e:
        print("Erreur fetch all unread: " + str(e))
        return []


def is_likely_personal(email):
    """Heuristique rapide (sans IA) : True si l'email semble personnel ou appelle une action."""
    subject = email["subject"].lower().strip()
    sender = email["sender"].lower()

    # Email de conversation (reponse ou transfert)
    if any(subject.startswith(p) for p in REPLY_PREFIXES):
        return True

    # Expediteur depuis un domaine personnel/generique
    for domain in PERSONAL_DOMAINS:
        if f"@{domain}" in sender:
            return True

    return False


def suggest_label(email, rules):
    """Cherche une regle matching. Les regles composites (domaine+sujet) sont prioritaires."""
    sender = email["sender"].lower()
    subject = email["subject"].lower()

    # 1. Regles composites domaine+mot-cle (plus specifiques)
    for pattern, label in rules.items():
        if "+" in pattern:
            domain_part, keyword = pattern.split("+", 1)
            if domain_part.lstrip("@") in sender and keyword in subject:
                return label

    # 2. Regles domaine seul
    for pattern, label in rules.items():
        if "+" not in pattern:
            if pattern.startswith("@") and pattern[1:] in sender:
                return label
            if pattern.startswith("subj:") and pattern[5:] in subject:
                return label

    return None


def apply_rules_to_unread(service, rules, max_results=None):
    """Applique les regles sur TOUS les non-lus, en protegeant les emails personnels."""
    emails = fetch_all_unread_emails(service)
    counts = {}
    skipped_personal = 0
    skipped_no_rule = 0

    for email in emails:
        # Protection : ne jamais toucher un email personnel ou de conversation
        if is_likely_personal(email):
            skipped_personal += 1
            continue
        label = suggest_label(email, rules)
        if label in LABELS_NO_AUTO:
            skipped_personal += 1
        elif label:
            apply_label_to_email(service, email["id"], label)
            counts[label] = counts.get(label, 0) + 1
        else:
            skipped_no_rule += 1

    return counts, skipped_personal, skipped_no_rule


def classify_with_ai(email, rules, api_key):
    if not api_key:
        return "Autre"
    rule_hint = ""
    if rules:
        rule_hint = "\nRegles: " + ", ".join(f"{p}->{l}" for p, l in list(rules.items())[:10])
    prompt = (
        f"Classe cet email dans un des labels: {', '.join(LABELS_DEFAULT)}\n"
        f"Securite = alertes connexion, verification identite, confirmation mdp, 2FA, acces suspect.\n"
        f"De: {email['sender']}\nObjet: {email['subject']}\nExtrait: {email['snippet']}"
        f"{rule_hint}\n\nReponds UNIQUEMENT avec le label exact."
    )
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": api_key, "content-type": "application/json", "anthropic-version": "2023-06-01"},
            json={"model": "claude-haiku-4-5-20251001", "max_tokens": 15, "messages": [{"role": "user", "content": prompt}]},
            timeout=15
        )
        label = r.json()["content"][0]["text"].strip()
        if label in LABELS_DEFAULT:
            return label
        for lbl in LABELS_DEFAULT:
            if lbl.lower() in label.lower():
                return lbl
        return "Autre"
    except Exception as e:
        print("Erreur AI classify: " + str(e))
        return "Autre"


def audit_classify_with_ai(email, rules, api_key):
    """Retourne un label si classifiable automatiquement, None si personnel/action requise."""
    if not api_key:
        return None
    rule_hint = ""
    if rules:
        rule_hint = "\nRegles: " + ", ".join(f"{p}->{l}" for p, l in list(rules.items())[:8])
    prompt = (
        f"Analyse cet email. Deux cas:\n"
        f"1. Email personnel, necessite une reponse/action, OU alerte de securite (connexion, 2FA, ajout tel, acces suspect, Steam/Google/Apple security) -> reponds: GARDER\n"
        f"2. Email automatique (newsletter, notif, commande, pub) -> reponds avec UN label parmi: {', '.join(LABELS_DEFAULT)}\n"
        f"En cas de doute, reponds GARDER.\n"
        f"De: {email['sender']}\nObjet: {email['subject']}\nExtrait: {email['snippet']}"
        f"{rule_hint}\n\nReponds UNIQUEMENT avec GARDER ou le label exact."
    )
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": api_key, "content-type": "application/json", "anthropic-version": "2023-06-01"},
            json={"model": "claude-haiku-4-5-20251001", "max_tokens": 15, "messages": [{"role": "user", "content": prompt}]},
            timeout=15
        )
        label = r.json()["content"][0]["text"].strip()
        if label == "GARDER":
            return None
        if label in LABELS_DEFAULT:
            return label
        for lbl in LABELS_DEFAULT:
            if lbl.lower() in label.lower():
                return lbl
        return None
    except Exception as e:
        print("Erreur audit classify: " + str(e))
        return None


def audit_classify_batch_with_ai(domain_samples, rules, api_key):
    """Classifie N groupes domaine en un seul appel IA. domain_samples = [(domain, email), ...]
    Retourne {domain: label_or_None}."""
    if not api_key or not domain_samples:
        return {}
    rule_hint = ""
    if rules:
        rule_hint = "\nRegles: " + ", ".join(f"{p}->{l}" for p, l in list(rules.items())[:8])
    items = "\n\n".join(
        f"{i+1}. De: {s['sender'][:70]}\nObjet: {s['subject'][:80]}\nExtrait: {s['snippet'][:120]}"
        for i, (_, s) in enumerate(domain_samples)
    )
    prompt = (
        f"Classe chaque email. Labels: {', '.join(LABELS_DEFAULT)}\n"
        f"Reponds GARDER si: personnel, reponse requise, alerte securite (2FA, connexion suspecte, acces compte).\n"
        f"Format strict, une ligne par email: '1: Label' ou '1: GARDER'{rule_hint}\n\n{items}"
    )
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": api_key, "content-type": "application/json", "anthropic-version": "2023-06-01"},
            json={"model": "claude-haiku-4-5-20251001", "max_tokens": len(domain_samples) * 15 + 50,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=30
        )
        text = r.json()["content"][0]["text"]
        results = {}
        for line in text.strip().split("\n"):
            m = re.match(r"(\d+)[:.]\s*(.+)", line.strip())
            if not m:
                continue
            idx = int(m.group(1)) - 1
            raw = m.group(2).strip()
            if not (0 <= idx < len(domain_samples)):
                continue
            domain = domain_samples[idx][0]
            if raw.upper() == "GARDER":
                results[domain] = None
            elif raw in LABELS_DEFAULT:
                results[domain] = raw
            else:
                for lbl in LABELS_DEFAULT:
                    if lbl.lower() in raw.lower():
                        results[domain] = lbl
                        break
        return results
    except Exception as e:
        print("Erreur batch classify: " + str(e))
        return {}


def get_or_create_label(service, name):
    try:
        result = service.users().labels().list(userId="me").execute()
        for lbl in result.get("labels", []):
            if lbl["name"].lower() == name.lower():
                return lbl["id"]
        new = service.users().labels().create(
            userId="me",
            body={"name": name, "labelListVisibility": "labelShow", "messageListVisibility": "show"}
        ).execute()
        return new["id"]
    except Exception as e:
        print("Erreur label: " + str(e))
        return None


def apply_label_to_email(service, email_id, label_name):
    try:
        label_id = get_or_create_label(service, label_name)
        if not label_id:
            return False
        service.users().messages().modify(
            userId="me", id=email_id,
            body={"addLabelIds": [label_id], "removeLabelIds": ["UNREAD"]}
        ).execute()
        return True
    except Exception as e:
        print("Erreur apply label: " + str(e))
        return False


def reset_gmail_labels(service, on_progress=None):
    """Retire TOUS les labels (user + categories) de toute la boite et remet en inbox non-lu."""
    try:
        # Collecte tous les labels a supprimer : user + categories Gmail
        all_labels_result = service.users().labels().list(userId="me").execute()
        remove_ids = [
            lbl["id"] for lbl in all_labels_result.get("labels", [])
            if lbl.get("type") == "user" or lbl["id"].startswith("CATEGORY_")
        ]

        # Pagination complete sur toute la boite hors spam/trash
        all_msg_ids = []
        params = {"userId": "me", "q": "-in:spam -in:trash", "maxResults": 500}
        result = service.users().messages().list(**params).execute()
        all_msg_ids.extend(m["id"] for m in result.get("messages", []))
        while "nextPageToken" in result:
            result = service.users().messages().list(**params, pageToken=result["nextPageToken"]).execute()
            all_msg_ids.extend(m["id"] for m in result.get("messages", []))

        if not all_msg_ids:
            return 0

        if on_progress:
            on_progress(len(all_msg_ids))

        body = {"addLabelIds": ["INBOX", "UNREAD"]}
        if remove_ids:
            body["removeLabelIds"] = remove_ids

        for i in range(0, len(all_msg_ids), 1000):
            batch = all_msg_ids[i:i + 1000]
            service.users().messages().batchModify(
                userId="me", body={**body, "ids": batch}
            ).execute()

        return len(all_msg_ids)
    except Exception as e:
        print("Erreur reset_gmail: " + str(e))
        return -1


def learn_rule(email, label, rules):
    """Cree une regle composite domaine+sujet pour les domaines generiques,
    domaine seul pour les domaines commerciaux specifiques."""
    sender = email.get("sender", "")
    m = re.search(r"@([\w.\-]+)", sender)

    stop = {"re:", "fwd:", "re", "fw", "tr", "le", "la", "les", "un", "une",
            "des", "de", "du", "et", "ou", "votre", "voici", "pour", "votre"}
    words = [
        w.lower() for w in re.split(r"\W+", email.get("subject", ""))
        if len(w) > 4 and w.lower() not in stop
    ]

    if m:
        domain = m.group(1).lower()
        domain_key = "@" + domain
        if domain in PERSONAL_DOMAINS:
            # Domaine generique : regle composite obligatoire (domaine+mot-cle sujet)
            if words:
                rules[f"{domain_key}+{words[0]}"] = label
        else:
            # Domaine commercial specifique : regle domaine seul
            rules[domain_key] = label
            # + regle composite pour plus de precision si on a un mot-cle
            if words:
                rules[f"{domain_key}+{words[0]}"] = label

    return rules

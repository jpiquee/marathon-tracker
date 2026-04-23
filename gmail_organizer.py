import os
import json
import re
import base64
import requests

GMAIL_RULES_FILE = "gmail_rules.json"
PENDING_EMAILS_FILE = "pending_emails.json"

LABELS_DEFAULT = [
    "Travail", "Personnel", "Newsletter", "Commande",
    "Finance", "Voyage", "Social", "Autre"
]


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
    """Commit gmail_rules.json into the repo so learning persists permanently."""
    token = os.environ.get("GITHUB_TOKEN", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "jpiquee/marathon-tracker")
    if not token:
        print("GITHUB_TOKEN manquant, règles non committées")
        return

    content = json.dumps(rules, ensure_ascii=False, indent=2)
    content_b64 = base64.b64encode(content.encode()).decode()
    api_url = f"https://api.github.com/repos/{repo}/contents/gmail_rules.json"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }

    sha = None
    r = requests.get(api_url, headers=headers, timeout=10)
    if r.status_code == 200:
        sha = r.json().get("sha")

    body = {
        "message": f"chore: apprentissage Gmail ({len(rules)} règles) [skip ci]",
        "content": content_b64,
        "branch": "main"
    }
    if sha:
        body["sha"] = sha

    r = requests.put(api_url, headers=headers, json=body, timeout=15)
    print("Commit règles Gmail: " + str(r.status_code))


def load_pending():
    try:
        with open(PENDING_EMAILS_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def save_pending(pending):
    with open(PENDING_EMAILS_FILE, "w") as f:
        json.dump(pending, f, ensure_ascii=False, indent=2)


def fetch_unread_emails(service, max_results=8):
    try:
        result = service.users().messages().list(
            userId="me", q="is:unread in:inbox", maxResults=max_results
        ).execute()
        emails = []
        for msg in result.get("messages", []):
            data = service.users().messages().get(
                userId="me", id=msg["id"], format="metadata",
                metadataHeaders=["Subject", "From"]
            ).execute()
            headers = {h["name"]: h["value"] for h in data["payload"]["headers"]}
            emails.append({
                "id": msg["id"],
                "subject": headers.get("Subject", "(sans objet)")[:100],
                "sender": headers.get("From", "inconnu")[:80],
                "snippet": data.get("snippet", "")[:150],
            })
        return emails
    except Exception as e:
        print("Erreur fetch emails: " + str(e))
        return []


def suggest_label(email, rules):
    sender = email["sender"].lower()
    subject = email["subject"].lower()
    for pattern, label in rules.items():
        if pattern.startswith("@") and pattern[1:] in sender:
            return label
        if pattern.startswith("subj:") and pattern[5:] in subject:
            return label
    return None


def classify_with_ai(email, rules, api_key):
    if not api_key:
        return "Autre"

    rule_hint = ""
    if rules:
        samples = list(rules.items())[:10]
        rule_hint = "\nRègles apprises: " + ", ".join(f"{p}→{l}" for p, l in samples)

    prompt = (
        f"Classe cet email dans un des labels: {', '.join(LABELS_DEFAULT)}\n"
        f"De: {email['sender']}\n"
        f"Objet: {email['subject']}\n"
        f"Extrait: {email['snippet']}"
        f"{rule_hint}\n\n"
        f"Réponds UNIQUEMENT avec le label exact, rien d'autre."
    )

    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "content-type": "application/json",
                "anthropic-version": "2023-06-01"
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 15,
                "messages": [{"role": "user", "content": prompt}]
            },
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


def learn_rule(email, label, rules):
    sender = email.get("sender", "")
    m = re.search(r"@([\w.\-]+)", sender)
    if m:
        rules["@" + m.group(1)] = label

    stop = {"re:", "fwd:", "re", "fw", "le", "la", "les", "un", "une",
            "des", "de", "du", "et", "ou", "votre", "voici", "pour"}
    words = [
        w.lower() for w in re.split(r"\W+", email.get("subject", ""))
        if len(w) > 5 and w.lower() not in stop
    ]
    if words:
        rules["subj:" + words[0]] = label

    return rules

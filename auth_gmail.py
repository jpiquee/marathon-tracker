"""
Script a executer UNE SEULE FOIS en local pour generer token.json
"""
from google_auth_oauthlib.flow import InstalledAppFlow
import json

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.labels",
]

flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
creds = flow.run_local_server(port=0)

with open("token.json", "w") as f:
    f.write(creds.to_json())

print("token.json genere avec succes !")
print("\nContenu a copier comme secret GitHub GMAIL_TOKEN :")
print("-" * 50)
with open("token.json") as f:
    print(f.read())

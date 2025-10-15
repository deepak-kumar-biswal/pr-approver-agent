import os
import json
import boto3
import urllib.request

SECRETS_ARN = os.environ.get("TEAMS_SECRET_ARN")

def _get_webhook_url(event):
    if event.get("teams_webhook_url"):
        return event["teams_webhook_url"]
    if SECRETS_ARN:
        sm = boto3.client('secretsmanager')
        val = sm.get_secret_value(SecretId=SECRETS_ARN)
        secret = val.get('SecretString')
        if secret:
            try:
                js = json.loads(secret)
                return js.get("url") or secret
            except Exception:
                return secret
    return None

def handler(event, context):
    """Post an Adaptive Card to Teams (incoming webhook).

    Inputs:
      - teams_webhook_url (optional if using Secrets)
      - card (dict) or 'text' string to render a simple card
    """
    url = _get_webhook_url(event)
    if not url:
        return {"error": "missing-webhook-url"}
    card = event.get("card")
    if not card:
        text = event.get("text") or "PR Review notification"
        card = {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": {
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "type": "AdaptiveCard",
                        "version": "1.4",
                        "body": [ { "type": "TextBlock", "text": text, "wrap": True } ]
                    }
                }
            ]
        }
    data = json.dumps(card).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as resp:
            _ = resp.read()
        return {"teams": "sent"}
    except Exception as e:
        return {"error": str(e)}

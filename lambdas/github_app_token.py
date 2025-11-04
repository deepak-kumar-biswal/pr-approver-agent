import os
import json
import time
import base64
import urllib.request
from typing import Optional

try:
    import jwt  # PyJWT
except Exception:  # pragma: no cover
    jwt = None

from lambdas._log import log

API = "https://api.github.com"


def _get_secret(arn: str) -> Optional[dict]:
    import boto3

    sm = boto3.client("secretsmanager")
    val = sm.get_secret_value(SecretId=arn)
    secret = val.get("SecretString")
    if secret:
        try:
            return json.loads(secret)
        except Exception:
            return {"private_key": secret}
    return None


def _app_jwt(app_id: str, private_key_pem: str) -> str:
    if not jwt:
        raise RuntimeError("PyJWT not available in runtime")
    now = int(time.time())
    payload = {
        "iat": now - 60,
        "exp": now + 540,
        "iss": app_id,
    }
    token = jwt.encode(payload, private_key_pem, algorithm="RS256")
    if isinstance(token, bytes):
        token = token.decode("utf-8")
    return token


def _get_installation_id(jwt_token: str, repo: str) -> int:
    # GET /repos/{owner}/{repo}/installation
    url = f"{API}/repos/{repo}/installation"
    req = urllib.request.Request(url, method="GET")
    req.add_header("Authorization", f"Bearer {jwt_token}")
    req.add_header("Accept", "application/vnd.github+json")
    with urllib.request.urlopen(req) as resp:
        j = json.loads(resp.read().decode("utf-8"))
        return int(j.get("id"))


def _create_installation_token(jwt_token: str, installation_id: int) -> str:
    url = f"{API}/app/installations/{installation_id}/access_tokens"
    req = urllib.request.Request(url, data=b"{}", method="POST")
    req.add_header("Authorization", f"Bearer {jwt_token}")
    req.add_header("Accept", "application/vnd.github+json")
    with urllib.request.urlopen(req) as resp:
        j = json.loads(resp.read().decode("utf-8"))
        return j.get("token")


def handler(event, context):
    """Mint a GitHub App installation token using a private key in Secrets Manager.

    Env:
      - GITHUB_APP_SECRET_ARN (JSON with keys: app_id, private_key, optional installation_id)
    Input (optional): { repo }
    Output: { token }
    """
    log("INFO", "github_app_token start", event)
    arn = os.environ.get("GITHUB_APP_SECRET_ARN")
    if not arn:
        return {"error": "missing-secret-arn"}
    secret = _get_secret(arn) or {}
    app_id = secret.get("app_id") or os.environ.get("GITHUB_APP_ID")
    private_key = secret.get("private_key")
    installation_id = secret.get("installation_id")
    if not (app_id and private_key):
        return {"error": "missing-app-credentials"}

    try:
        jwt_token = _app_jwt(str(app_id), private_key)
        if not installation_id:
            repo = event.get("repo")
            if not repo:
                return {"error": "missing-repo-for-installation-lookup"}
            installation_id = _get_installation_id(jwt_token, repo)
        token = _create_installation_token(jwt_token, int(installation_id))
        log("INFO", "installation token minted", event)
        return {"token": token}
    except Exception as e:
        log("ERROR", "mint token failed", event, error=str(e))
        return {"error": str(e)}

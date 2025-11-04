import os
import json
import time
import urllib.request
from lambdas._log import log

try:
    import jwt
except Exception:  # pragma: no cover
    jwt = None

API = "https://api.github.com"


def _get_secret(arn: str):
    import boto3

    sm = boto3.client("secretsmanager")
    val = sm.get_secret_value(SecretId=arn)
    secret = val.get("SecretString")
    if secret:
        try:
            return json.loads(secret)
        except Exception:
            return {"private_key": secret}
    return {}


def _app_jwt(app_id: str, private_key_pem: str) -> str:
    if not jwt:
        raise RuntimeError("PyJWT not available in runtime")
    now = int(time.time())
    payload = {"iat": now - 60, "exp": now + 540, "iss": app_id}
    token = jwt.encode(payload, private_key_pem, algorithm="RS256")
    if isinstance(token, bytes):
        token = token.decode("utf-8")
    return token


def _installation_token(jwt_token: str, repo: str, installation_id: int = None) -> str:
    if not installation_id:
        url = f"{API}/repos/{repo}/installation"
        req = urllib.request.Request(url, method="GET")
        req.add_header("Authorization", f"Bearer {jwt_token}")
        req.add_header("Accept", "application/vnd.github+json")
        with urllib.request.urlopen(req) as resp:
            j = json.loads(resp.read().decode("utf-8"))
            installation_id = int(j.get("id"))
    url = f"{API}/app/installations/{installation_id}/access_tokens"
    req = urllib.request.Request(url, data=b"{}", method="POST")
    req.add_header("Authorization", f"Bearer {jwt_token}")
    req.add_header("Accept", "application/vnd.github+json")
    with urllib.request.urlopen(req) as resp:
        j = json.loads(resp.read().decode("utf-8"))
        return j.get("token")


def _merge(repo: str, pr_number: int, token: str, method: str = "merge"):
    url = f"{API}/repos/{repo}/pulls/{pr_number}/merge"
    body = {"merge_method": method}
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="PUT")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def handler(event, context):
    """Auto-merge a PR when guardrails allow.

    Inputs: repo, pr_number, token (optional), or GH App creds via Secrets.
    Env: GITHUB_APP_SECRET_ARN (contains app_id, private_key, optional installation_id)
    """
    log("INFO", "github_merge start", event)
    repo = event.get("repo")
    pr = event.get("pr_number")
    token = event.get("token")
    method = event.get("method") or "squash"
    if not (repo and pr):
        return {"error": "missing-repo-or-pr"}
    if not token:
        arn = os.environ.get("GITHUB_APP_SECRET_ARN")
        if not arn:
            return {"error": "missing-token-and-secret-arn"}
        secret = _get_secret(arn)
        app_id = secret.get("app_id") or os.environ.get("GITHUB_APP_ID")
        private_key = secret.get("private_key")
        if not (app_id and private_key):
            return {"error": "missing-app-credentials"}
        jwt_token = _app_jwt(str(app_id), private_key)
        token = _installation_token(jwt_token, repo, secret.get("installation_id"))
    try:
        res = _merge(repo, int(pr), token, method)
        log("INFO", "merge attempted", event, merged=res.get("merged"))
        return {"status": "merged" if res.get("merged") else "not-merged", "sha": res.get("sha")}
    except Exception as e:
        log("ERROR", "merge failed", event, error=str(e))
        return {"error": str(e)}

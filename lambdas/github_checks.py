import os
import json
import urllib.request
from datetime import datetime
import boto3
from lambdas._log import log


API = "https://api.github.com"
CWM = boto3.client("cloudwatch")
S3 = boto3.client("s3")


def _post(url: str, token: str, body: dict):
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _conclusion(verdict: str) -> str:
    # Map our verdict to GitHub Checks conclusions
    v = (verdict or "").lower()
    if v == "green":
        return "success"
    if v == "amber":
        return "neutral"
    if v == "red":
        return "failure"
    return "neutral"


def _signed_url(bucket: str, key: str, expires: int = 3600) -> str:
    try:
        return S3.generate_presigned_url(
            "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=expires
        )
    except Exception:
        return ""


def _emit_metrics(verdict: dict, start_ts: str | None):
    try:
        v = (verdict.get("verdict") or "").upper()
        conf = float(verdict.get("confidence") or 0.0)
        dims = [{"Name": "Verdict", "Value": v or "UNKNOWN"}]
        metrics = [
            {
                "MetricName": "VerdictCount",
                "Dimensions": dims,
                "Unit": "Count",
                "Value": 1.0,
            },
            {
                "MetricName": "Confidence",
                "Dimensions": dims,
                "Unit": "None",
                "Value": conf,
            },
        ]
        if start_ts:
            try:
                # allow ISO8601 or epoch millis
                if start_ts.isdigit():
                    ms = int(start_ts)
                    start = datetime.fromtimestamp(ms / 1000)
                else:
                    start = datetime.fromisoformat(start_ts.replace("Z", "+00:00"))
                now = datetime.utcnow()
                dur_ms = max(0, int((now - start).total_seconds() * 1000))
                metrics.append(
                    {
                        "MetricName": "ReviewTimeMs",
                        "Dimensions": [],
                        "Unit": "Milliseconds",
                        "Value": float(dur_ms),
                    }
                )
            except Exception:
                pass
        CWM.put_metric_data(Namespace="PRReview", MetricData=metrics)
    except Exception:
        pass


def handler(event, context):
    """Create a GitHub Check Run for the PR SHA.

    Inputs:
      - repo (org/repo)
      - sha (commit SHA to attach check to)
      - verdict { verdict, confidence, drivers, markdown }
      - token (optional) else env GITHUB_TOKEN (installation token recommended)
    """
    log("INFO", "github_checks start", event)
    repo = event.get("repo")
    sha = event.get("sha")
    verdict = (event.get("verdict") or {})
    token = event.get("token") or os.environ.get("GITHUB_TOKEN")
    if not (repo and sha and token):
        log("ERROR", "missing repo/sha/token", event)
        return {"error": "missing-repo-sha-or-token"}

    name = "IAM PR Review"
    conclusion = _conclusion(verdict.get("verdict"))
    summary = verdict.get("markdown") or "Automated review completed."
    title = f"{verdict.get('verdict','-').upper()} (confidence {verdict.get('confidence',0):.2f})"
    # Optional artifact link
    artifact_url = event.get("artifact_url")
    if not artifact_url and event.get("artifact_key"):
        bucket = event.get("bucket") or os.environ.get("BUCKET_NAME")
        if bucket:
            artifact_url = _signed_url(bucket, event["artifact_key"]) or None

    body = {
        "name": name,
        "head_sha": sha,
        "status": "completed",
        "conclusion": conclusion,
        "output": {
            "title": title,
            "summary": summary[:65535],
        },
    }
    if artifact_url:
        body["output"]["text"] = f"Artifacts: {artifact_url}"
    base = f"{API}/repos/{repo}/check-runs"
    try:
        res = _post(base, token, body)
        log("INFO", "check created", event, id=res.get("id"))
        _emit_metrics(verdict, event.get("start_ts"))
        return {"status": "check-created", "id": res.get("id")}
    except Exception as e:
        log("ERROR", "create check failed", event, error=str(e))
        return {"error": str(e)}

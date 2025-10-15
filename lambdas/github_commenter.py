import os
import json
import urllib.request

def _post(url: str, token: str, body: dict):
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))

def handler(event, context):
    """Post a GitHub PR comment.

    Inputs:
      - repo (org/repo)
      - pr_number OR commit_sha + pr_url fallback
      - markdown (comment body)
      - token (optional, otherwise from env GITHUB_TOKEN)
    """
    repo = event.get("repo")
    pr_number = event.get("pr_number")
    markdown = event.get("markdown") or "(no content)"
    token = event.get("token") or os.environ.get("GITHUB_TOKEN")
    if not (repo and token):
        return {"error": "missing-repo-or-token"}

    base = f"https://api.github.com/repos/{repo}"
    try:
        if pr_number:
            url = f"{base}/issues/{pr_number}/comments"
            res = _post(url, token, {"body": markdown})
        else:
            # fallback to a commit comment if only sha provided
            sha = event.get("sha")
            if not sha:
                return {"error": "missing-pr_number-and-sha"}
            url = f"{base}/commits/{sha}/comments"
            res = _post(url, token, {"body": markdown})
        return {"status": "comment-posted", "id": res.get("id")}
    except Exception as e:
        return {"error": str(e)}

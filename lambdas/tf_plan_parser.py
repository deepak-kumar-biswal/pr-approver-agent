import json
import os
import boto3
from typing import Any, Dict, List, Tuple, Set

IAM_TYPES = {
    "aws_iam_role",
    "aws_iam_policy",
    "aws_iam_role_policy",
    "aws_iam_role_policy_attachment",
    "aws_iam_policy_attachment",
    "aws_iam_user_policy",
    "aws_iam_group_policy",
}

def _safe_json_loads(s: Any):
    if isinstance(s, str):
        try:
            return json.loads(s)
        except Exception:
            return None
    return None

def _collect_modules(address: str) -> List[str]:
    # terraform addresses like: module.foo.module.bar.aws_iam_role.this
    parts = address.split(".")
    modules = []
    i = 0
    while i < len(parts):
        if parts[i] == "module" and i + 1 < len(parts):
            modules.append(f"module.{parts[i+1]}")
            i += 2
        else:
            i += 1
    return modules

def _scan_policy_for_wildcards(policy_doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    findings = []
    if not policy_doc:
        return findings
    stmts = policy_doc.get("Statement", [])
    if isinstance(stmts, dict):
        stmts = [stmts]
    for idx, st in enumerate(stmts):
        action = st.get("Action")
        if action == "*":
            findings.append({"statement": idx, "reason": "Action:* detected"})
        elif isinstance(action, list) and "*" in action:
            findings.append({"statement": idx, "reason": "Action list includes *"})
    return findings

def _parse_changes(plan: Dict[str, Any]) -> Dict[str, Any]:
    changes = plan.get("resource_changes", []) or []
    total = len(changes)
    iam_by_type: Dict[str, Dict[str, int]] = {}
    roles_affected: Set[str] = set()
    modules_set: Set[str] = set()
    wildcard_actions: List[Dict[str, Any]] = []
    accounts_from_tags: Set[str] = set()

    for rc in changes:
        rtype = rc.get("type")
        address = rc.get("address", "")
        change = rc.get("change", {})
        actions = change.get("actions", [])
        after = change.get("after")
        before = change.get("before")

        # module collection
        for m in _collect_modules(address):
            modules_set.add(m)

        # init counters
        if rtype in IAM_TYPES:
            iam_by_type.setdefault(rtype, {"create": 0, "update": 0, "delete": 0, "no-op": 0})
            for a in actions:
                if a in iam_by_type[rtype]:
                    iam_by_type[rtype][a] += 1

            # roles affected
            if rtype == "aws_iam_role":
                name = None
                if isinstance(after, dict):
                    name = after.get("name") or after.get("name_prefix")
                if not name and isinstance(before, dict):
                    name = before.get("name") or before.get("name_prefix")
                if not name:
                    # fallback to address suffix
                    name = address.split(".")[-1]
                roles_affected.add(str(name))

            # wildcard scan for policies
            policy_json = None
            if rtype == "aws_iam_policy":
                if isinstance(after, dict):
                    policy_json = _safe_json_loads(after.get("policy"))
                if not policy_json and isinstance(before, dict):
                    policy_json = _safe_json_loads(before.get("policy"))
            elif rtype in {"aws_iam_role_policy", "aws_iam_user_policy", "aws_iam_group_policy"}:
                # inline policies carry 'policy' attribute as JSON string
                if isinstance(after, dict):
                    policy_json = _safe_json_loads(after.get("policy"))
                if not policy_json and isinstance(before, dict):
                    policy_json = _safe_json_loads(before.get("policy"))

            for finding in _scan_policy_for_wildcards(policy_json or {}):
                wildcard_actions.append({
                    "address": address,
                    **finding,
                })

            # collect account tags if present
            for obj in (after, before):
                if isinstance(obj, dict):
                    tags = obj.get("tags") or {}
                    for k in ["AccountId", "account_id", "aws_account_id"]:
                        val = tags.get(k)
                        if val:
                            accounts_from_tags.add(str(val))

    return {
        "total_resources": total,
        "iam": {
            "by_type": iam_by_type,
            "roles_affected": sorted(roles_affected),
            "wildcard_actions": wildcard_actions,
        },
        "modules": sorted(modules_set),
        "accounts": sorted(accounts_from_tags),
    }

def handler(event, context):
    """Read plan.json from S3 and emit a compact diff structure."""
    s3 = boto3.client('s3')
    bucket = event.get('bucket')
    key = event.get('plan_key')  # e.g., <run-id>/plan.json
    if not bucket or not key:
        return {"error":"missing bucket/plan_key"}
    try:
        body = s3.get_object(Bucket=bucket, Key=key)['Body'].read()
    except Exception as e:
        return {"error": f"s3-get-failed: {e}"}
    try:
        plan = json.loads(body)
    except Exception as e:
        return {"error": f"invalid-plan-json: {e}"}
    summary = _parse_changes(plan)
    return {"status": "ok", "summary": summary}

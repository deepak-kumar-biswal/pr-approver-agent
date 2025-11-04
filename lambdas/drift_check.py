import os
import boto3
from typing import Dict, Any, List
from lambdas._log import log

ASSUME_ROLE_NAME = os.environ.get("SPOKE_READONLY_ROLE", "CrossAccountReadOnlyRole")

def _assume(account_id: str, role_name: str) -> boto3.Session:
    sts = boto3.client("sts")
    arn = f"arn:aws:iam::{account_id}:role/{role_name}"
    creds = sts.assume_role(RoleArn=arn, RoleSessionName="pr-drift-check")['Credentials']
    return boto3.Session(
        aws_access_key_id=creds['AccessKeyId'],
        aws_secret_access_key=creds['SecretAccessKey'],
        aws_session_token=creds['SessionToken'],
    )

def _list_roles(iam) -> List[str]:
    names = []
    paginator = iam.get_paginator('list_roles')
    for page in paginator.paginate():
        for r in page.get('Roles', []):
            names.append(r.get('RoleName'))
    return names

def _attached_policies(iam, role_name: str) -> List[str]:
    arns = []
    paginator = iam.get_paginator('list_attached_role_policies')
    for page in paginator.paginate(RoleName=role_name):
        for p in page.get('AttachedPolicies', []):
            arns.append(p.get('PolicyArn'))
    return arns

def handler(event, context):
    """Assume spoke read-only role(s) and compare current IAM vs expected.

    Input:
      - event.summary.iam.roles_affected: roles that plan intends to change
      - event.spoke_accounts: list of spoke account IDs to check
    Output:
      - drift: none/suspect
      - details: mismatches by account/role
    """
    log("INFO", "drift_check start", event)
    summary = (event or {}).get("summary", {})
    iam_sum = summary.get("iam", {})
    intended_roles = set(iam_sum.get("roles_affected") or [])
    accounts = event.get("spoke_accounts") or summary.get("accounts") or []
    if not accounts or not intended_roles:
        log("INFO", "drift_check skip - no accounts or roles", event)
        return {"drift": "none", "reason": "no-accounts-or-roles"}

    mismatches = {}
    for acct in accounts:
        try:
            sess = _assume(acct, ASSUME_ROLE_NAME)
            iam = sess.client('iam')
            present = set(_list_roles(iam))
            # roles intended to exist should be in present (if create/update)
            missing = [r for r in intended_roles if r not in present]
            details = {"missing_roles": missing}
            # Optionally inspect attachments for roles that do exist
            for r in intended_roles.intersection(present):
                details.setdefault("roles", {})[r] = {
                    "attached_policies": _attached_policies(iam, r)
                }
            if missing:
                mismatches[acct] = details
        except Exception as e:
            log("ERROR", "drift_check assume/list failed", event, account=acct, error=str(e))
            mismatches[acct] = {"error": str(e)}

    status = "none" if not mismatches else "suspect"
    log("INFO", "drift_check done", event, status=status, accounts=len(accounts))
    return {"drift": status, "details": mismatches}

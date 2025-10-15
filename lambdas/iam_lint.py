import json

REQUIRED_TAGS = {"Owner", "CostCenter"}

def _contains(action_field, needle):
    if action_field is None:
        return False
    if isinstance(action_field, str):
        return action_field == needle or action_field == "*" or needle == "*"
    if isinstance(action_field, list):
        return any(_contains(a, needle) for a in action_field)
    return False

def lint_policy(policy):
    v = []
    stmts = policy.get("Statement", [])
    if isinstance(stmts, dict):
        stmts = [stmts]
    for st in stmts:
        action = st.get("Action")
        resource = st.get("Resource")
        cond = st.get("Condition", {})
        # Wildcard actions
        if action == "*":
            v.append("Action:* detected – use least-privilege explicit actions")
        # iam:PassRole must be scoped
        if _contains(action, "iam:PassRole") and resource == "*":
            v.append("iam:PassRole must be scoped to specific role ARNs")
        # sts assume role must have conditions if resource is *
        if ( _contains(action, "sts:AssumeRole") or _contains(action, "sts:AssumeRoleWithWebIdentity") ) and resource == "*" and not cond:
            v.append("sts:AssumeRole on * requires restrictive Condition")
        # s3:PutObject should enforce SSE if resource is *
        if _contains(action, "s3:PutObject") and resource == "*":
            sse = cond.get("StringEquals", {}).get("s3:x-amz-server-side-encryption")
            if not sse:
                v.append("s3:PutObject must enforce SSE via condition")
    return v

def lint_trust(trust, org_prefix="arn:aws:iam::${ORG_ACCOUNT_PREFIX}"):
    v = []
    principal = (trust or {}).get("Principal", {})
    cond = (trust or {}).get("Condition", {})
    aws_principal = principal.get("AWS")
    if aws_principal and not str(aws_principal).startswith(org_prefix):
        ext = cond.get("StringEquals", {}).get("sts:ExternalId")
        if not ext:
            v.append("External principal without ExternalId condition")
    return v

def lint_metadata(md):
    w = []
    if not md:
        return w
    tags = set(md.get("tags", {}).keys())
    missing = REQUIRED_TAGS - tags
    if missing:
        w.append("Resource missing required tags (Owner, CostCenter)")
    return w

def handler(event, context):
    """Run IAM policy lint rules and trust checks.
    Expect event to contain keys: policy (dict), trust (dict), metadata (optional)
    """
    policy = event.get("policy", {})
    trust = event.get("trust", {})
    metadata = event.get("metadata", {})
    violations = []
    warnings = []
    violations += lint_policy(policy)
    violations += lint_trust(trust)
    warnings += lint_metadata(metadata)
    return {"violations": violations, "warnings": warnings, "valid": len(violations) == 0}

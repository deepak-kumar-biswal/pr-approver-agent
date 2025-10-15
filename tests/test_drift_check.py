from lambdas import drift_check as mod

def test_drift_check_no_accounts_or_roles():
    out = mod.handler({"summary": {"iam": {"roles_affected": []}}, "spoke_accounts": []}, None)
    assert out["drift"] == "none"
    assert out.get("reason") == "no-accounts-or-roles"

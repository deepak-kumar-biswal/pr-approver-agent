import json
from lambdas import tf_plan_parser as mod

def test_parse_changes_basic():
    plan = {
        "resource_changes": [
            {"type": "aws_iam_role", "address": "module.auth.aws_iam_role.main", "change": {"actions": ["create"], "after": {"name": "MyRole", "tags": {"AccountId": "111111111111"}}}},
            {"type": "aws_iam_policy", "address": "aws_iam_policy.p", "change": {"actions": ["create"], "after": {"policy": json.dumps({"Version":"2012-10-17","Statement":[{"Action":"*","Effect":"Allow","Resource":"*"}]})}}}
        ]
    }
    out = mod._parse_changes(plan)
    assert out["total_resources"] == 2
    assert "aws_iam_role" in out["iam"]["by_type"]
    assert out["iam"]["wildcard_actions"]
    assert out["modules"] == ["module.auth"]
    assert out["accounts"] == ["111111111111"]

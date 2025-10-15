from lambdas import iam_lint as mod

def test_iam_lint_rules():
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {"Action": "*", "Effect": "Allow", "Resource": "*"},
            {"Action": ["iam:PassRole"], "Effect": "Allow", "Resource": "*"},
        ]
    }
    trust = {"Principal": {"AWS": "arn:aws:iam::999999999999:root"}, "Condition": {}}
    out = mod.handler({"policy": policy, "trust": trust, "metadata": {"tags": {}}}, None)
    assert not out["valid"]
    assert any("Action:*" in v for v in out["violations"]) 
    assert any("PassRole" in v for v in out["violations"]) 

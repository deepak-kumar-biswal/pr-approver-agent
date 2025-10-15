from lambdas import risk_score as mod

def test_risk_score_aggregation():
    event = {
        "lint": {"violations": ["a", "b"]},
        "plan": {"summary": {"iam": {"wildcard_actions": [{}, {}]}}},
        "drift": {"drift": "suspect"},
        "impact": {"blast_radius": "medium"}
    }
    out = mod.handler(event, None)
    assert out["risk"] in ("amber", "red")
    assert out["confidence"] <= 0.7
    assert any("wildcards" in d for d in out["drivers"]) 

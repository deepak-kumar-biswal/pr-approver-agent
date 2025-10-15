from lambdas import impact_map as mod

def test_impact_map_basic():
    event = {"summary": {"modules": ["module.a", "module.a"], "accounts": ["111", "222"]}}
    out = mod.handler(event, None)
    assert out["blast_radius"] in ("small", "medium", "large")
    assert out["accounts"] == ["111", "222"]
    assert out["modules"] == ["module.a"]

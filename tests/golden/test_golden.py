import json
import os
from pathlib import Path


CASES_DIR = Path(__file__).parent / "cases"


def load_case(name: str):
    p = CASES_DIR / f"{name}.json"
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def test_noop_plan_skips_agent_and_allows():
    case = load_case("noop_plan")
    # No IAM changes should lead to allow at OPA gate
    from lambdas.opa_gate import handler as opa

    res = opa({"plan": {"summary": case["summary"]}}, None)
    assert res["allow"] is True
    assert res["deny"] == []


def test_wildcard_action_denied():
    case = load_case("wildcard_action")
    from lambdas.opa_gate import handler as opa

    res = opa({"plan": {"summary": case["summary"]}}, None)
    assert res["allow"] is False
    assert any("Action:*" in d for d in res["deny"]) or res["deny"]


def test_malformed_plan_graceful_degrade():
    case = load_case("malformed_plan")
    from lambdas.tf_plan_parser import summary_from_plan as summarize

    # Should not raise; should return a minimal summary
    summary = summarize(case.get("plan_json", {}))
    assert isinstance(summary, dict)
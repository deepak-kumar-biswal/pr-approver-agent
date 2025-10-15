from lambdas import github_commenter as gh
from lambdas import teams_notifier as teams

def test_github_commenter_missing_reqs():
    out = gh.handler({"markdown": "hello"}, None)
    assert "error" in out

def test_teams_notifier_missing_url():
    out = teams.handler({"text": "hi"}, None)
    assert "error" in out

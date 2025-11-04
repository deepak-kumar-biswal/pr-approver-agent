from typing import Dict, Any, List
from lambdas._log import log

def _unique(seq: List[str]) -> List[str]:
    return sorted({str(x) for x in seq if x})

def handler(event, context):
    """Map modules→accounts and summarize blast radius.

    Inputs:
      - event.summary (from tf_plan_parser) with keys: modules, accounts
      - or event.modules/accounts directly as fallback

    Output:
      - accounts: unique list of affected AWS account IDs (best-effort from tags)
      - modules: unique list of module addresses involved in the change
      - blast_radius: naive classification small/medium/large based on counts
    """
    summary = (event or {}).get("summary", {})
    modules = summary.get("modules") or event.get("modules") or []
    accounts = summary.get("accounts") or event.get("accounts") or []
    modules = _unique(modules)
    accounts = _unique(accounts)

    size = len(accounts) + len(modules)
    if size <= 3:
        radius = "small"
    elif size <= 10:
        radius = "medium"
    else:
        radius = "large"

    out = {"accounts": accounts, "modules": modules, "blast_radius": radius}
    log("INFO", "impact_map computed", event, accounts=len(accounts), modules=len(modules), radius=radius)
    return out

import json
import os
import subprocess
from typing import Any, Dict, List
from lambdas._log import log


def _deny_from_plan(summary: Dict[str, Any]) -> List[str]:
    denies = []
    if not summary:
        return denies
    wildcards = ((summary.get("iam") or {}).get("wildcard_actions") or [])
    if wildcards:
        denies.append("Action:* detected – use least-privilege explicit actions")
    return denies


def _opa_cli_available() -> bool:
    return os.path.exists(os.path.join(os.getcwd(), "opa"))


def _opa_eval(input_obj: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate policies/iam.rego using bundled OPA CLI.
    Returns dict with keys deny (list) and warn (list).
    """
    opa_path = os.path.join(os.getcwd(), "opa")
    wasm_path = os.path.join(os.getcwd(), "policies", "policy.wasm")
    data_path = os.path.join(os.getcwd(), "policies", "data.json")
    # Prefer WASM if available, else fall back to source rego
    has_wasm = os.path.exists(wasm_path)
    policy_path = os.path.join(os.getcwd(), "policies", "iam.rego")
    if not os.path.exists(opa_path) or (not has_wasm and not os.path.exists(policy_path)):
        return {"deny": [], "warn": []}
    os.makedirs("/tmp", exist_ok=True)
    input_path = "/tmp/input.json"
    with open(input_path, "w", encoding="utf-8") as f:
        json.dump(input_obj, f, separators=(",", ":"))
    if has_wasm:
        cmd = [
            opa_path,
            "eval",
            "-f",
            "json",
            "--wasm",
            wasm_path,
            "-i",
            input_path,
            "data.iam.rules",
        ]
        if os.path.exists(data_path):
            cmd[6:6] = ["-d", data_path]
    else:
        cmd = [
            opa_path,
            "eval",
            "-f",
            "json",
            "-d",
            policy_path,
            "-i",
            input_path,
            "data.iam.rules",
        ]
    try:
        res = subprocess.run(cmd, capture_output=True, check=True)
        out = json.loads(res.stdout.decode("utf-8"))
        # OPA eval JSON format: result[0].expressions[0].value.{deny,warn}
        result = (((out.get("result") or [{}])[0]).get("expressions") or [{}])[0].get("value") or {}
        deny = result.get("deny") or []
        warn = result.get("warn") or []
        # Normalize to list of strings
        deny = [str(x) for x in deny]
        warn = [str(x) for x in warn]
        return {"deny": deny, "warn": warn}
    except Exception as e:
        # On any failure, degrade silently – upstream fallback will decide
        return {"deny": [], "warn": [f"opa_eval_error:{e}"]}


def handler(event, context):
    """OPA/Conftest gate placeholder.

    If explicit policy/trust/metadata are provided, delegate to deterministic checks later.
    Otherwise, derive minimal deny rules from plan summary (e.g., wildcard actions).
    Output contract: { deny: [..], warn: [..], allow: bool }
    """
    log("INFO", "opa_gate start", event)
    summary = ((event.get("plan") or {}).get("summary")) or event.get("summary") or {}
    deny: List[str] = []
    warn: List[str] = []

    # Prefer full OPA evaluation with the bundled CLI + rego; fall back to simple heuristic
    input_obj = {
        "policy": (event.get("policy") or {}),
        "trust": (event.get("trust") or {}),
        "metadata": (event.get("metadata") or {}),
        "summary": summary or {},
    }
    if _opa_cli_available():
        eva = _opa_eval(input_obj)
        deny = eva.get("deny", [])
        warn = eva.get("warn", [])
    if not deny:
        # Heuristic checks if OPA produced nothing or CLI missing
        deny = _deny_from_plan(summary)
    allow = len(deny) == 0
    out = {"deny": deny, "warn": warn, "allow": allow}
    log("INFO", "opa_gate done", event, allow=allow, deny=len(deny))
    return out

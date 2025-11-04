import json
import os
from datetime import datetime
from typing import Any, Dict, Optional


def _ctx_fields(event: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    e = event or {}
    # Common context propagation for observability
    # Prefer explicit fields in event, then environment variables
    return {
        "run_id": e.get("run_id") or os.environ.get("RUN_ID"),
        "repo": e.get("repo") or os.environ.get("REPO"),
        "sha": e.get("sha") or os.environ.get("SHA"),
    }


def log(level: str, message: str, event: Optional[Dict[str, Any]] = None, **fields: Any) -> None:
    """Minimal structured logger printing JSON lines suitable for CloudWatch Logs.

    Usage: log("INFO", "parsed plan", event, items=10)
    """
    rec: Dict[str, Any] = {
        "ts": datetime.utcnow().isoformat() + "Z",
        "level": level.upper(),
        "message": message,
    }
    rec.update({k: v for k, v in _ctx_fields(event).items() if v is not None})
    if fields:
        rec.update(fields)
    try:
        print(json.dumps(rec, separators=(",", ":")))
    except Exception:
        # Fallback to plain text if serialization fails
        print(f"{rec['ts']} {rec['level']} {rec['message']} {fields}")

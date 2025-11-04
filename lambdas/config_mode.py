import os
from lambdas._log import log
import boto3

SSM_PARAM = os.environ.get("MODE_PARAM", "pr-review/mode")


def handler(event, context):
    """Load mode from SSM Parameter pr-review/mode or fallback to 'comment_only'.
    Output: { mode }
    """
    log("INFO", "config_mode start", event)
    ssm = boto3.client("ssm")
    mode = "comment_only"
    try:
        resp = ssm.get_parameter(Name=SSM_PARAM)
        val = (resp.get("Parameter") or {}).get("Value")
        if val:
            mode = val.strip()
    except Exception as e:
        log("ERROR", "ssm get failed", event, error=str(e))
    log("INFO", "config_mode done", event, mode=mode)
    return {"mode": mode}

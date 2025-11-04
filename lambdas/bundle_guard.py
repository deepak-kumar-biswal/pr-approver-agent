import os
import boto3
from lambdas._log import log


DDB = boto3.client("dynamodb")
TABLE_NAME = os.environ.get("TABLE_NAME")
BUNDLE_HASH = os.environ.get("BUNDLE_HASH", "")


def handler(event, context):
    """Gatekeeper for prompt/rule bundle changes.

    Contract:
    - Reads bundle hash from env BUNDLE_HASH (or event["bundle_hash"]).
    - Looks up item pk = CONFIG#BUNDLE#<hash> in DDB table, expects { approved: BOOL }.
    - Returns { approved: bool, hash: str, reason: str }
    """
    log("INFO", "bundle_guard start", event)
    if not TABLE_NAME:
        log("ERROR", "missing TABLE_NAME", event)
        return {"approved": False, "hash": BUNDLE_HASH, "reason": "no-table"}

    bh = (event.get("bundle_hash") if isinstance(event, dict) else None) or BUNDLE_HASH
    if not bh:
        log("ERROR", "missing bundle hash", event)
        return {"approved": False, "hash": "", "reason": "no-hash"}

    pk = f"CONFIG#BUNDLE#{bh}"
    try:
        res = DDB.get_item(TableName=TABLE_NAME, Key={"pk": {"S": pk}})
        item = res.get("Item") or {}
        approved = (item.get("approved") or {}).get("BOOL") if isinstance(item.get("approved"), dict) else None
        if approved is True:
            log("INFO", "bundle approved", event, bundle_hash=bh)
            return {"approved": True, "hash": bh, "reason": "approved"}
        else:
            log("ERROR", "bundle not approved", event, bundle_hash=bh)
            return {"approved": False, "hash": bh, "reason": "not-approved"}
    except Exception as e:
        log("ERROR", "bundle_guard ddb error", event, error=str(e))
        return {"approved": False, "hash": bh, "reason": "ddb-error"}

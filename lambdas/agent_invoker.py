import json
import os
import uuid
import boto3
from botocore.exceptions import BotoCoreError, ClientError
from lambdas._log import log


AGENT_ID = os.environ.get("AGENT_ID")
AGENT_ALIAS_ID = os.environ.get("AGENT_ALIAS_ID", "default")
TABLE_NAME = os.environ.get("TABLE_NAME")


def _session_id(event):
    return event.get("run_id") or str(uuid.uuid4())


def _input_text(event):
    # Minimal instruction; Agent tools/KB should drive depth.
    plan_total = (((event.get("plan") or {}).get("summary") or {}).get("total_resources"))
    risk = ((event.get("risk") or {}).get("risk"))
    drift = ((event.get("drift") or {}).get("drift"))
    return (
        "Review IAM-related Terraform changes and produce a JSON verdict with fields: "
        "verdict (green|amber|red), confidence (0..1), drivers (list of strings), markdown (summary). "
        f"Signals: total_plan_resources={plan_total}, precomputed_risk={risk}, drift={drift}."
    )


def _safe_json_block(text: str):
    # Try to extract a JSON object from free-form text
    if not text:
        return None
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        blob = text[start : end + 1]
        try:
            return json.loads(blob)
        except Exception:
            return None
    return None


def handler(event, context):
    """Invoke Bedrock Agent and return a structured verdict.

    Inputs (event): repo, sha, run_id; plus prior stage outputs under keys: plan, lint, risk, drift, impact.
    Environment: AGENT_ID, AGENT_ALIAS_ID
    Output: { verdict, confidence, drivers, markdown } or raises to trigger SFN fallback.
    """
    log("INFO", "agent_invoker start", event)
    agent_id = event.get("agent_id") or AGENT_ID
    agent_alias_id = event.get("agent_alias_id") or AGENT_ALIAS_ID
    if not agent_id:
        log("ERROR", "missing AGENT_ID", event)
        raise ValueError("AGENT_ID not set")

    client = boto3.client("bedrock-agent-runtime")
    session_id = _session_id(event)
    input_text = _input_text(event)

    # Attach compact context as sessionAttributes to assist the Agent
    # Keep size modest to avoid request limits
    context_min = {
        "repo": event.get("repo"),
        "sha": event.get("sha"),
        "run_id": event.get("run_id"),
        "plan_summary": (event.get("plan") or {}).get("summary"),
        "lint": {"violations": (event.get("lint") or {}).get("violations", [])},
        "risk": event.get("risk"),
        "drift": event.get("drift"),
        "impact": event.get("impact"),
    }

    try:
        resp = client.invoke_agent(
            agentId=agent_id,
            agentAliasId=agent_alias_id,
            sessionId=session_id,
            inputText=input_text,
            sessionState={
                "sessionAttributes": {
                    "context_json": json.dumps(context_min, separators=(",", ":"))
                }
            },
        )
    except (ClientError, BotoCoreError) as e:
        log("ERROR", "InvokeAgent failed", event, error=str(e))
        # Let Step Functions retry/catch
        raise

    # Collect streaming output text, if any
    text_chunks = []
    try:
        if "completion" in resp:
            # Non-streaming (future-proof)
            text_chunks.append(resp.get("completion") or "")
        elif "responseStream" in resp:
            # Streaming events (preferred)
            stream = resp["responseStream"]
            for event_part in stream:
                # Event parts can include: "chunk" with bytes, "trace", "returnControl" etc.
                chunk = event_part.get("chunk")
                if chunk and "bytes" in chunk:
                    text_chunks.append(chunk["bytes"].decode("utf-8", errors="ignore"))
        else:
            # Unknown shape; try to stringify
            text_chunks.append(json.dumps(resp))
    except Exception as e:
        log("ERROR", "stream parse failed", event, error=str(e))
        # Don't fail the run on decode issues; agent may still have invoked tools that updated state elsewhere
        pass

    final_text = "".join(text_chunks)
    parsed = _safe_json_block(final_text)
    if not parsed:
        # Produce a conservative output to avoid blocking reviews
        log("ERROR", "no JSON verdict in agent output; falling back", event)
        raise RuntimeError("agent-output-missing-json")

    # Minimal contract normalization
    verdict = parsed.get("verdict") or (parsed.get("risk") or "amber")
    confidence = float(parsed.get("confidence") or 0.7)
    drivers = parsed.get("drivers") or []
    markdown = parsed.get("markdown") or "Automated review completed."

    tokens_estimated = max(1, len(final_text) // 4) if final_text else 0
    out = {
        "verdict": verdict,
        "confidence": confidence,
        "drivers": drivers,
        "markdown": markdown,
        "agent_session_id": session_id,
        "tokens_estimated": tokens_estimated,
    }
    log("INFO", "agent_invoker done", event, verdict=verdict, confidence=confidence)
    # Optional audit write
    try:
        if TABLE_NAME and event.get("run_id"):
            ddb = boto3.client("dynamodb")
            item = {
                "run_id": {"S": str(event.get("run_id"))},
                "created_at": {"S": context.aws_request_id if hasattr(context, 'aws_request_id') else session_id},
                "repo": {"S": str(event.get("repo") or '')},
                "sha": {"S": str(event.get("sha") or '')},
                "verdict": {"S": str(verdict)},
                "confidence": {"N": str(confidence)},
                "tokens_estimated": {"N": str(tokens_estimated)},
            }
            ddb.put_item(TableName=TABLE_NAME, Item=item)
    except Exception as e:
        log("ERROR", "ddb audit write failed", event, error=str(e))
    return out

from lambdas._log import log


def handler(event, context):
    """Compute risk category from signals.

    Inputs expected in event:
      - lint.violations (list)
      - plan.summary.iam.wildcard_actions (list)
      - drift.drift (none/suspect)
      - impact.blast_radius (small/medium/large)

    Returns: risk (green/amber/red), confidence [0..1], drivers (list)
    """
    drivers = []
    score = 0
    # base score by violations
    violations = ((event.get("lint") or {}).get("violations")) or []
    if violations:
        score += min(3, len(violations))
        drivers.append(f"lint_violations:{len(violations)}")
    # wildcard actions in policies
    wildcard = ((((event.get("plan") or {}).get("summary") or {}).get("iam") or {}).get("wildcard_actions") or [])
    if wildcard:
        score += min(3, len(wildcard))
        drivers.append(f"wildcards:{len(wildcard)}")
    # drift
    drift = (event.get("drift") or {}).get("drift")
    if drift == "suspect":
        score += 2
        drivers.append("drift:suspect")
    # blast radius
    radius = (event.get("impact") or {}).get("blast_radius")
    if radius == "medium":
        score += 1
        drivers.append("radius:medium")
    elif radius == "large":
        score += 2
        drivers.append("radius:large")

    # translate score to risk and confidence
    if score <= 1:
        risk = "green"
        confidence = 0.9
    elif score <= 3:
        risk = "amber"
        confidence = 0.7
    else:
        risk = "red"
        confidence = 0.5

    out = {"risk": risk, "confidence": confidence, "drivers": drivers}
    log("INFO", "risk scored", event, risk=risk, confidence=confidence, drivers=len(drivers))
    return out

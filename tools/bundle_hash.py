import hashlib
from pathlib import Path


TARGETS = [
    Path("policies/iam.rego"),
    Path("lambdas/agent_invoker.py"),
    Path("lambdas/opa_gate.py"),
    Path("lambdas/github_checks.py"),
]


def compute_hash():
    h = hashlib.sha256()
    for p in TARGETS:
        if p.exists():
            h.update(p.read_bytes())
    return h.hexdigest()


if __name__ == "__main__":
    print(compute_hash())
# Bedrock IAM PR Reviewer – CFN Pack

**Version:** 2025-11-04

This repository contains a production‑ready, **CloudFormation-first** implementation of a Bedrock Agent–assisted
PR review pipeline for Terraform IAM changes. It starts in **comment‑only** mode and can be promoted to **assisted** and
ultimately **auto‑approve** with strict guardrails and bundle‑governed prompts/policies.

## What’s Included

- CloudFormation stacks (in `cfn/`):
  - `pr-review-core.yaml` – KMS, S3 artifacts bucket, DynamoDB audit table, SNS, (optional) Secrets for Teams
  - `pr-review-iam.yaml` – IAM roles & policies (GitHub OIDC, Step Functions, Lambda execs, Bedrock agent role, cross‑account read‑only)
  - `pr-review-compute.yaml` – Lambda tools (parsers, linters, risk, drift, OPA gate with WASM, GitHub Checks, GitHub App helpers, bundle guard, quarterly report, etc.) with DLQs and alarms
  - `pr-review-orchestration.yaml` – EventBridge + Step Functions (OPA → deterministic checks → Agent → Checks → approve/merge), plus expanded CloudWatch dashboard
  - `pr-review-agent.yaml` – Bedrock Agent + Knowledge Base (includes action groups for tool calls)
- Lambda functions in `lambdas/` (Python 3.12) including:
  - `tf_plan_parser`, `iam_lint`, `risk_score`, `drift_check`, `impact_map`
  - `opa_gate` (uses bundled OPA CLI with preferred WASM; falls back gracefully)
  - `agent_invoker` (Bedrock Agents runtime streaming, structured verdict)
  - `github_commenter`, `github_checks` (Check Runs + metrics + optional signed artifact URLs)
  - `teams_notifier`, `quarterly_report` (ReportLab PDF)
  - `config_mode` (reads SSM mode), `github_app_token` and `github_merge` (optional auto‑merge), `bundle_guard` (governance)
- OPA policy starter in `policies/` with CI‑built WASM bundle
- GitHub Actions:
  - `deploy-compute.yml` – packages lambdas, builds OPA WASM, uploads to S3, computes bundle hash and deploys
  - `golden.yml` – Golden PR regression suite (nightly and on main)
  - `pr-merged.yml` – example integration trigger
- `DESIGN.md` & `ARCHITECTURE.ascii` – overview and rollout
- `SAMPLE-TEAMS-CARD.json` – Adaptive Card template
- Flow charts: see `docs/FLOW.md`

## Parameters You Must Set

- **Account IDs:** hub + spokes in CFN params
- **GitHub org/repo:** used in OIDC trust conditions
- **Regions:** Bedrock/Agent region + your preferred build region (ensure Bedrock Agents enabled)
- **Optional:**
  - Teams integration by providing a webhook secret (Secrets Manager ARN)
  - GitHub App private key secret (Secrets Manager ARN) for auto‑merge
  - `ArtifactsPrefix` to scope S3 access for least privilege

## Deploy

See the new deployment guide for step‑by‑step instructions, parameters, and pre‑requisites: `DEPLOYMENT.md`.

## GitHub → AWS (OIDC)

- Ensure the **OIDC provider** is created (included in `pr-review-iam.yaml`).
- Limit the trust to `refs/heads/develop` (default). Modify as needed.

## Modes and Auto‑Approve

Set the mode via SSM Parameter `pr-review/mode` (the `config_mode` lambda reads this):

- `comment_only` (default)
- `suggest_approve`
- `auto_approve`

Guardrails to auto‑approve include:

- OPA gate clean (deny = []),
- Risk and deterministic checks OK,
- Agent verdict green with confidence ≥ threshold,
- Drift = none.

Optional GitHub App‑based auto‑merge requires a private key secret ARN passed to compute stack.

## Quarterly PDF report (overview)

- Lambda: `pr-quarterly-report` scans DynamoDB `PRRuns` and summarizes KPIs (counts per verdict, failures, time saved est.)
- Output written to S3 at `reports/YYYY-QN.pdf` (KMS-encrypted). Schedule: `cron(0 3 1 JAN,APR,JUL,OCT ? *)`.
- Rich PDF via ReportLab is packaged by the compute workflow; falls back to text if the lib is unavailable.

## Observability and Dashboard

- Dashboard name: `pr-review` with widgets for Step Functions executions, Lambda errors, DDB throttles, SNS failures, verdict counts, and review time p50/p90.
- GitHub Checks Lambda emits custom metrics: `PRReview/VerdictCount`, `PRReview/Confidence`, `PRReview/ReviewTimeMs`.
- Alarms provided for critical Lambdas (AgentInvoker, OPA Gate, GitHub Checks, Merge); DLQs enabled.

## Governance and Safety

- Prompt/policy bundle governance: each deploy computes a SHA256 over key files and passes it to the compute stack (`BundleHash`). The orchestrator calls `bundle_guard` to require DDB approval (item `CONFIG#BUNDLE#<hash>`).
- Tools provided: `tools/bundle_hash.py` (compute), `tools/approve_bundle.py` (approve in DDB).
- IAM hardening: permissions boundary applied to tool Lambdas and optional S3 prefix scoping via `ArtifactsPrefix`.

## Golden PR Suite

- A small seed regression suite lives under `tests/golden/` and runs via `.github/workflows/golden.yml` nightly and on main. Add 50–100 JSON cases to lock behavior when prompts/policies evolve.

## Local development

- Run tests: `python -m pytest -q`
- Deterministic functions have unit tests; Agent calls are retried and have a static fallback path.
- Packaging is handled by `.github/workflows/deploy-compute.yml` and produces zips in `dist/lambda/` before uploading to S3.

---

© 2025-11-04 – Drop this folder into a new repo and iterate.

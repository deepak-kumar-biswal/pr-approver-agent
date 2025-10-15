# Bedrock IAM PR Reviewer – CFN Pack

**Version:** 2025-10-14

This repository contains a production‑ready, **CloudFormation-first** implementation of a Bedrock Agent–assisted
PR review pipeline for Terraform IAM changes. It starts in **comment‑only** mode and can be promoted to **assisted** and
ultimately **auto‑approve** with strict guardrails.

## What’s Included

- CloudFormation stacks (in `cfn/`):
  - `pr-review-core.yaml` – KMS, S3 artifacts bucket, DynamoDB audit table, SNS, (optional) Secrets for Teams
  - `pr-review-iam.yaml` – IAM roles & policies (GitHub OIDC, Step Functions, Lambda execs, Bedrock agent role, cross‑account read‑only)
  - `pr-review-compute.yaml` – Lambda tools (parsers, linters, risk, drift, commenting, Teams)
  - `pr-review-orchestration.yaml` – EventBridge rule + Step Functions state machine
  - `pr-review-agent.yaml` – Bedrock Agent + Knowledge Base (native or Custom resource fallback)
  - CloudWatch Dashboard – `ReviewDashboard` resource and JSON under `dashboards/pr-dashboard.json`
  - Quarterly PDF report generator Lambda + EventBridge schedule
- Lambda function stubs in `lambdas/` (Python 3.12), with clear TODOs
- Example OPA/Conftest policy starter in `policies/`
- GitHub Actions workflow in `.github/workflows/pr-merged.yml`
- `DESIGN.md` – deep architecture & rollout plan
- `ARCHITECTURE.ascii` – copy‑pastable ASCII diagram for docs
- `SAMPLE-TEAMS-CARD.json` – Adaptive Card example

## Parameters You Must Set

- **Account IDs:** hub + spokes in CFN params
- **GitHub org/repo:** used in OIDC trust conditions
- **Regions:** Bedrock/Agent region + your preferred build region
- **Optional:** enable Teams integration by providing a webhook secret

## Deploy (one-time bootstrap)

> Replace placeholders like `111111111111`, `your-org`, `your-repo`, and choose your region.

```bash
REGION=us-east-1
HUB=111111111111

aws cloudformation deploy --region $REGION --stack-name pr-review-core   --template-file cfn/pr-review-core.yaml   --capabilities CAPABILITY_NAMED_IAM   --parameter-overrides ArtifactsBucketName=iam-pr-review-artifacts DataKeyAlias=alias/pr-review-kms CreateTeamsIntegration=false

aws cloudformation deploy --region $REGION --stack-name pr-review-iam   --template-file cfn/pr-review-iam.yaml   --capabilities CAPABILITY_NAMED_IAM   --parameter-overrides HubAccountId=$HUB GitHubOrg=your-org GitHubRepo=your-repo
  
aws cloudformation deploy --region $REGION --stack-name pr-review-compute   --template-file cfn/pr-review-compute.yaml   --capabilities CAPABILITY_NAMED_IAM

aws cloudformation deploy --region $REGION --stack-name pr-review-agent   --template-file cfn/pr-review-agent.yaml   --capabilities CAPABILITY_NAMED_IAM   --parameter-overrides UseCustomAgentResource=true

aws cloudformation deploy --region $REGION --stack-name pr-review-orchestration   --template-file cfn/pr-review-orchestration.yaml   --capabilities CAPABILITY_NAMED_IAM

# Optional: Verify the CloudWatch dashboard
# Open CloudWatch → Dashboards → pr-review

# Optional: The quarterly report Lambda is scheduled automatically (1st of Jan/Apr/Jul/Oct at 03:00 UTC)
```

## GitHub → AWS (OIDC)

- Ensure the **OIDC provider** is created (included in `pr-review-iam.yaml`).
- Limit the trust to `refs/heads/develop` (default). Modify as needed.

## Promotion to Auto‑Approve

Set the mode in DynamoDB item `config:mode` or via SSM Parameter `pr-review/mode`:

- `comment_only` (default)
- `suggest_approve`
- `auto_approve`

Guardrails (OPA clean, risk=green, confidence ≥ threshold, drift=ok, blast radius bounded) must pass to auto‑approve.

## Quarterly PDF report (overview)

- Lambda: `pr-quarterly-report` scans DynamoDB `PRRuns` and summarizes KPIs (counts per verdict, failures, time saved est.)
- Output written to S3 at `reports/YYYY-QN.pdf` (KMS-encrypted). Schedule: `cron(0 3 1 JAN,APR,JUL,OCT ? *)`.
- Minimal PDF renderer is embedded to avoid external deps; swap to ReportLab later for rich formatting.

## CloudWatch dashboard

- Dashboard name: `pr-review` with widgets for Step Functions executions, Lambda errors, DDB throttles, and SNS failures.
- JSON source lives at `dashboards/pr-dashboard.json`, embedded into CFN for convenience.

---

© 2025-10-14 – Drop this folder into a new repo and iterate.

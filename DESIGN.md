# DESIGN.md – Bedrock IAM PR Reviewer

## Objectives
- Automate consistent enforcement of IAM/Terraform guardrails.
- Reduce PR cycle time while *increasing* security signal quality.
- Full auditability with artifacts, decisions, and costs logged.

## High-Level Flow
1. **Trigger**: PR merges into `develop` → GitHub Action collects `plan.json`, changed files, metadata → S3.
2. **EventBridge** fires `pr-merged` detail → **Step Functions** orchestrates:
   - OPA/Conftest static gate on HCL/policies
   - Bedrock Agent review (RAG + Lambda tools)
   - Risk scorer (heuristics)
3. **Verdict** synthesized → PR comment posted; SNS/Teams summary sent; DDB updated.
4. **Promotion path** to auto‑approve gated by confidence + drift + blast radius.

## Components
- **S3 Artifacts (KMS)** – versioned storage of plans & inputs.
- **DynamoDB (PAYG)** – run registry + audit trail.
- **Lambda Tools** – deterministic helpers: TF plan parser, IAM linter, risk score, impact map, drift check.
- **Bedrock Agent** – uses KB (rules, examples, exceptions) + tools to produce structured JSON → converted into Markdown.
- **Step Functions** – retries, DLQs, metrics, error handling.
- **SNS / Teams (optional)** – summaries to approvers / security leads.
- **CloudWatch Dashboards** – KPIs management cares about (cycle time, verdict mix, trends).

## Security & Governance
- OIDC from GitHub to AWS with minimal S3 + PutEvents only.
- KMS encryption for S3/DDB/Secrets; no secrets in prompts.
- Permissions boundaries (optional) for Lambda to limit dangerous APIs.
- Cross‑account reads via constrained **CrossAccountReadOnlyRole** in spokes.
- Agent/tool prompts + rule versions are **hash‑pinned** in the audit log.

## Rollout
- **Shadow (comment‑only)** → **Assisted** → **Auto‑approve** per module/env cohort.
- Golden test suite (50–100 PR cases) gates any rule/prompt updates.
- Feedback loop: approvers mark calls good/bad → weekly review.

## Management Metrics (Dashboards)
- PRs reviewed / week; median time saved
- Verdict mix (Green/Amber/Red), top violations, mean-time-to-fix
- False positive rate trend
- Auto‑approve adoption over time
- Token spend / run and monthly total

## Failure Modes & Mitigations
- Tool failure → automatic fallback to static gates + human review; clear alert
- Model uncertainty → amber + request specific evidence (drift proof, account map)
- Repo sprawl → enforce repo metadata, module registry, and tagging via OPA

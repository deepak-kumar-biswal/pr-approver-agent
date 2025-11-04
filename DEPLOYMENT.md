# Deployment Guide

This guide walks you through deploying the IAM PR Reviewer stacks and wiring the CI workflow.

## Prerequisites

- AWS account with permissions to deploy CloudFormation stacks and create IAM roles/policies
- Bedrock Agents enabled in your chosen region
- GitHub repository with Actions enabled
- AWS CLI configured locally (optional, workflows can handle deploys)
- S3 bucket name to host Lambda artifacts (created by `pr-review-core`)
- (Optional) Microsoft Teams webhook (stored in Secrets Manager)
- (Optional) GitHub App for auto-merge (private key stored in Secrets Manager)

## Stacks overview

- Core: KMS (CMK), S3 artifacts bucket, DynamoDB table, SNS topic
- IAM: OIDC trust for GitHub Actions, roles for Lambdas/Step Functions/Events, Bedrock runtime access
- Compute: All Lambda tools, DLQs, alarms, permissions boundary, scoped S3 prefix (optional), exports for orchestrator
- Agent: Bedrock Agent + Knowledge Base (with action groups wired)
- Orchestration: EventBridge rule + Step Functions pipeline + CloudWatch dashboard

## 1) Bootstrap Core and IAM

Deploy once per environment (adjust parameters for your org/repo/regions).

- pr-review-core.yaml: creates KMS, S3, DDB, SNS
- pr-review-iam.yaml: creates IAM roles/policies and OIDC trust

## 2) Package and upload Lambda code

Use the GitHub workflow `Package & Deploy Compute` (`.github/workflows/deploy-compute.yml`). It:

- Zips each Lambda with `_log.py`
- Downloads OPA CLI and builds a WASM bundle from `policies/iam.rego`
- Packages GitHub App helpers with dependencies (PyJWT, cryptography)
- Packages `quarterly_report` with ReportLab
- Uploads zips to the artifacts S3 bucket

Inputs you provide when dispatching the workflow:

- aws-region (default: us-east-1)
- artifacts-bucket (the bucket from the core stack)
- code-prefix (default: `lambda/`)

The deploy step in the workflow computes a bundle hash and passes it to the compute stack automatically.

## 3) Deploy Compute stack

Deployed by the same workflow after packaging. Parameters:

- BucketName: artifacts bucket
- CodeS3Prefix: prefix containing the zips (e.g., `lambda/`)
- BundleHash: auto-computed by CI from the current repo state
- Optional:
  - TeamsSecretArn: Secrets Manager ARN for Teams webhook
  - GitHubAppSecretArn: Secrets Manager ARN for GitHub App private key (for auto-merge)
  - ArtifactsPrefix: narrow S3 access to `s3://BucketName/ArtifactsPrefix*`

Outputs export the function ARNs for the orchestrator.

## 4) Deploy Agent stack

Deploy `cfn/pr-review-agent.yaml`. You can use the provided resource with action groups. Ensure your Agent has access to its Knowledge Base and that the region supports Agents.

## 5) Deploy Orchestration stack

Deploy `cfn/pr-review-orchestration.yaml`. It imports function ARNs exported by the compute stack.

Pipeline flow:

- ParsePlan → LoadMode → BundleGuard (governance) → OPAGate → Deterministic checks → AgentReview → GitHub Checks → ApprovalDecide → SuggestApprove/AutoMerge → CommentPR → NotifyTeams

## 6) Configure runtime

- Mode: set SSM parameter `pr-review/mode` to one of:
  - `comment_only` (default)
  - `suggest_approve`
  - `auto_approve`
- Governance: approve the bundle hash in DDB using the helper tool:
  - `python tools/approve_bundle.py <TableName> <BundleHash>`
- Secrets:
  - Teams webhook JSON in Secrets Manager (if using Teams). Provide ARN via compute stack parameter.
  - GitHub App private key in Secrets Manager (if using auto-merge). Provide ARN via compute stack parameter.

## 7) GitHub integration

- Ensure GitHub OIDC role is trusted for your repo/branch (configured in IAM stack)
- Add or update workflows:
  - `.github/workflows/deploy-compute.yml` (already included)
  - `.github/workflows/golden.yml` for nightly golden tests
- If you use a GitHub App for auto-merge, install it in your org/repo and note the installation ID; the merge Lambda mints an installation token using the secret.

## 8) Validate and observe

- Push to main or dispatch the compute workflow to package and deploy
- Open CloudWatch Dashboard `pr-review` to monitor SFn executions, Lambda errors, verdict counts, and review time
- Check GitHub Check Runs attached to your commits

## 9) Auto-merge (optional)

- Set mode to `auto_approve`
- Ensure GitHub App secret ARN is configured on the compute stack
- Confirm the approvals gates pass (OPA deny=[], green verdict with high confidence, no drift)

## 10) Golden PR Suite

- Add JSON cases under `tests/golden/cases/` to capture key scenarios
- The `golden.yml` workflow runs nightly and on main to prevent regressions

## Troubleshooting

- "Bundle not approved": approve the current bundle hash in DDB
- OPA errors: the OPA gate falls back to heuristics; verify `policies/iam.rego` compiles to WASM in CI
- GitHub API rate limit: the Checks Lambda logs and returns error; you can add retries in the orchestrator if needed
- ReportLab missing: the quarterly report falls back to text; ensure packaging ran to include ReportLab
- Missing artifacts: verify the S3 bucket/prefix and that the compute deploy picked up your latest zips

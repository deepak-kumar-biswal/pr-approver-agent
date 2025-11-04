# Flow charts – IAM PR Reviewer

This document presents flow charts for both the CI/CD packaging+deploy process and the runtime orchestration pipeline, including governance and auto‑merge logic.

## 1) CI/CD packaging and deploy (GitHub Actions)

```mermaid
flowchart LR
  GH["GitHub Repo"] --> GHA["GitHub Actions: deploy-compute.yml"]
  GHA -->|"Zip lambdas (incl. _log.py)"| S3[("S3 Artifacts Bucket")]
  GHA -->|"Build OPA WASM (policies/iam.rego)"| S3
  GHA -->|"Package GH App + ReportLab"| S3
  GHA -->|"Compute BundleHash (tools/bundle_hash.py)"| CFN["CloudFormation: pr-review-compute"]
  GHA -->|"Deploy stacks (Core/IAM/Compute/Agent/Orchestration)"| CFN
  GHA --> GOLDEN["Golden PR Suite (golden.yml)"]
  GOLDEN -->|"Nightly & on main"| GH
```

Key outputs

- Uploaded Lambda zips (including opa_gate with WASM, github_app_token/merge, quarterly_report with ReportLab)
- Compute stack deployed with `BundleHash` for governance
- Nightly golden tests enforce regression safety

## 2) Runtime orchestration

```mermaid
flowchart TD
  subgraph Triggers
    EVB["EventBridge: pr-merged"]
  end

  subgraph Orchestration
    SFN["Step Functions: pr-review-orchestrator"]
  end

  EVB --> SFN

  SFN --> Parse["Lambda: tf_plan_parser"]
  Parse --> Mode["Lambda: config_mode (SSM)"]
  Mode --> Guard["Lambda: bundle_guard (DDB)"]
  Guard -- approved --> OPA["Lambda: opa_gate"]
  Guard -- not approved --> BlockComment["Lambda: github_commenter (governance block)"] --> Teams["Lambda: teams_notifier"] --> End1((End))

  %% Deterministic checks
  OPA --> Lint["Lambda: iam_lint"]
  Lint --> Risk["Lambda: risk_score"]
  Risk --> Drift["Lambda: drift_check"]
  Drift --> Impact["Lambda: impact_map"]
  Impact --> Agent["Lambda: agent_invoker (Bedrock Agent)"]

  %% Agent error fallback
  Agent -- error/timeout --> Fallback["StaticVerdictFallback from risk"]
  Fallback --> Checks

  Agent --> Checks["Lambda: github_checks (metrics + optional artifacts)"]
  Checks --> Decision{Approval Decide}

  Decision -- auto_approve --> Merge["Lambda: github_merge (GitHub App)"] --> CommentPR["Lambda: github_commenter"]
  Decision -- suggest_approve --> Suggest["Lambda: github_commenter (suggest approve)"] --> CommentPR
  Decision -- default --> CommentPR

  CommentPR --> Teams
  Teams --> End2((End))
```

Notes

- OPA gate short‑circuits if `deny` contains violations → red path comment (in code: OPAVerdictBlock).
- AgentReview is retried with backoff and falls back to static verdict if Bedrock has errors.
- GitHub Checks always posts a result (success/neutral/failure) with a compact summary and emits CloudWatch metrics.

## 3) Approval/merge branches

```mermaid
flowchart LR
  Checks["GitHub Checks"] --> Decision{Green?\nConf>=0.9?\nNo drift?\nMode?}
  Decision -- mode=auto_approve --> Merge["GitHub Merge"] --> CommentPR
  Decision -- mode=suggest_approve --> Suggest["Comment: Suggested approve"] --> CommentPR
  Decision -- otherwise --> CommentPR
  CommentPR --> Teams["Teams Notify"]
```

Guardrails

- OPA deny = []
- Deterministic checks OK (lint/risk/drift/impact constraints)
- Agent verdict green with high confidence
- Drift = none
- Mode ∈ {suggest_approve, auto_approve}

## 4) Error handling & retries (summary)

- Bedrock/throttle/errors → Step Functions retry with backoff; after max attempts, fallback to static verdict
- GitHub API failures for Checks/Comments → logged; Checks path can be retried at the state machine level if needed
- Governance not approved → immediate block comment + Teams notification
- Missing/invalid plan → parser returns error; pipeline degrades gracefully; golden tests cover malformed/no‑op plans

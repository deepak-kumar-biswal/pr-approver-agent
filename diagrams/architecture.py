"""
Generate the architecture diagram using diagrams-as-code.

Requires:
- Python package: diagrams (already in requirements-dev.txt)
- System package: Graphviz (dot)

Usage (Windows CMD):
  C:/Python313/python.exe diagrams/architecture.py
This will create architecture.png/svg in the same folder.
"""
from diagrams import Cluster, Diagram, Edge
from diagrams.aws.compute import Lambda
from diagrams.aws.integration import Eventbridge, StepFunctions
from diagrams.aws.database import Dynamodb
from diagrams.aws.storage import S3
from diagrams.aws.security import IAM, KMS, SecretsManager
from diagrams.aws.management import Cloudwatch, SystemsManagerParameterStore
from diagrams.aws.management import Cloudformation
from diagrams.aws.ml import Sagemaker
from diagrams.aws.general import Client
from diagrams.aws.migration import ApplicationDiscoveryService as KnowledgeBase
from diagrams.aws.integration import SQS, SNS
from diagrams.onprem.vcs import Github
from diagrams.onprem.ci import GithubActions


with Diagram(
    "IAM PR Review – Architecture",
    filename="architecture",
    show=False,
    outformat=["png", "svg"],
    direction="TB",
):
    gh = Github("GitHub Repo")
    gha = GithubActions("GitHub Actions")
    teams = Client("Microsoft Teams")

    with Cluster("AWS Account (PR Review)"):
        # Core
        with Cluster("Core"):
            bucket = S3("Artifacts & Reports Bucket")
            table = Dynamodb("PRRuns Table")
            kms = KMS("KMS CMK")
            topic = SNS("SNS Topic")

        # IAM
        with Cluster("IAM & Access"):
            oidc = IAM("GitHub OIDC Trust")
            tools_role = IAM("Tools Exec Role")
            states_role = IAM("States Role")

        # Management & Observability
        with Cluster("Management & Observability"):
            cfn = Cloudformation("CloudFormation Stacks")
            cw = Cloudwatch("CloudWatch Dashboard/Alarms")
            ssm = SystemsManagerParameterStore("SSM: pr-review/mode")
            secrets = SecretsManager("Secrets (Teams/GH App)")

        # Orchestration
        with Cluster("Orchestration"):
            evb = Eventbridge("EventBridge: pr-merged")
            sfn = StepFunctions("Step Functions: Orchestrator")

        # Compute (Lambdas)
        with Cluster("Compute (Lambdas)"):
            # deterministic tools
            with Cluster("Deterministic Gates"):
                tfplan = Lambda("tf_plan_parser")
                opa = Lambda("opa_gate")
                lint = Lambda("iam_lint")
                risk = Lambda("risk_score")
                drift = Lambda("drift_check")
                impact = Lambda("impact_map")

            agent_invoker = Lambda("agent_invoker")
            gh_comment = Lambda("github_commenter")
            gh_checks = Lambda("github_checks")
            teams_notifier = Lambda("teams_notifier")
            quarterly = Lambda("quarterly_report")
            config_mode = Lambda("config_mode")
            gh_app_token = Lambda("github_app_token")
            gh_merge = Lambda("github_merge")
            bundle_guard = Lambda("bundle_guard")
            dlq = SQS("Lambda DLQ")

        # Bedrock & KB (represented with SageMaker + KB placeholder if Bedrock icon is unavailable)
        with Cluster("Bedrock Agent & Knowledge Base"):
            bedrock = Sagemaker("Bedrock Agent")
            kb = KnowledgeBase("Knowledge Base")

    # CI packaging/deploy flow
    gh >> gha >> Edge(label="package & upload") >> bucket
    gha >> Edge(label="deploy CFN") >> cfn
    gha >> Edge(label="emit events") >> evb

    # Runtime trigger
    gh >> Edge(label="pr-merged event") >> evb >> sfn

    # State machine tasks
    sfn >> Edge(label="ParsePlan") >> tfplan
    sfn >> Edge(label="LoadMode") >> config_mode >> ssm
    sfn >> Edge(label="BundleGuard") >> bundle_guard >> table
    sfn >> Edge(label="OPA Gate") >> opa
    sfn >> lint
    sfn >> risk
    sfn >> drift
    sfn >> impact
    sfn >> Edge(label="AgentReview") >> agent_invoker >> bedrock
    sfn >> Edge(label="GitHub Checks") >> gh_checks >> gh
    sfn >> Edge(label="CommentPR") >> gh_comment >> gh
    sfn >> Edge(label="NotifyTeams") >> teams_notifier >> teams
    sfn >> Edge(label="Quarterly Report (scheduled)") >> quarterly
    sfn >> Edge(label="(optional) AutoMerge") >> gh_merge >> gh

    # Data paths and dependencies
    tfplan >> Edge(label="read/write plan.json, reports") >> bucket
    quarterly >> Edge(label="write report pdf") >> bucket
    agent_invoker >> Edge(style="dashed", label="audit") >> table
    lint >> Edge(style="dashed") >> kms
    opa >> Edge(style="dashed") >> bucket
    gh_checks >> Edge(style="dashed", label="metrics") >> cw

    # Secrets and parameters
    gh_merge >> Edge(style="dotted", label="GH App secret") >> secrets
    teams_notifier >> Edge(style="dotted", label="Teams webhook") >> secrets

    # DLQ wiring (representative)
    for fn in [tfplan, opa, lint, risk, drift, impact, agent_invoker, gh_comment, gh_checks, teams_notifier, quarterly, config_mode, gh_app_token, gh_merge, bundle_guard]:
        fn >> Edge(color="firebrick", style="dashed", label="DLQ") >> dlq

    # Access & roles context
    gha >> Edge(style="dotted", label="assume role") >> oidc
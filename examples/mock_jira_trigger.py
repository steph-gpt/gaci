"""
Mock Jira Trigger — Demo Script
================================
Simulates a Jira webhook for a feature moving to 'QA Ready'.
Runs the full GACI pipeline end-to-end without requiring a real Jira instance.

What this demonstrates:
1. Orchestrator receives the trigger and reads mock registry fields
2. CS Documentation Agent calls Claude and generates a draft
3. Draft is registered as a pending HITL approval
4. Mock SME approval is processed
5. Approved content is written to knowledge-repo/example-org/

Usage:
    cp .env.example .env
    # Add your ANTHROPIC_API_KEY to .env
    pip install -r requirements.txt
    python examples/mock_jira_trigger.py

Output:
    A fully structured markdown file in knowledge-repo/example-org/
    An audit log entry in audit.db
    Console output showing each step of the pipeline
"""

import os
import sys
import logging
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("mock-trigger")

# ── Mock data — edit these to test different scenarios ────────────────────────

MOCK_JIRA_ID = "PROD-1234"
MOCK_NEW_STATUS = "QA Ready"

MOCK_REGISTRY = {
    "jira_id": MOCK_JIRA_ID,
    "product_name": "SentinelOne",
    "feature_name": "SentinelOne v8 Upgrade",
    "description": (
        "Major platform upgrade from SentinelOne v7 to v8. Key changes include: "
        "the Deep Visibility module has been replaced with a unified visibility layer; "
        "endpoint agents now auto-update silently by default; "
        "MFA is now mandatory for all console users. "
        "This upgrade affects all customers on the managed SOC plan."
    ),
    "product_status": "Active",
    "content_scope": ["CS"],  # Only CS for MVP — add "Incident" when that agent is built
    "deprecation_reason": None,
    "successor_feature": None,
    "sunset_date": None,
}

MOCK_APPROVER = {
    "name": "jane.smith@example-org.com",
    "department": "customer-service",
    "owner_sme": "jane.smith@example-org.com",
    "co_owner_departments": [],
    "co_owner_smes": [],
    "co_owner_subtask_keys": [],
    "audience": ["sales", "product-marketing"],
    "jira_url": f"https://example-org.atlassian.net/browse/{MOCK_JIRA_ID}",
}

# ─────────────────────────────────────────────────────────────────────────────


class MockJiraConnector:
    """
    Replaces the real JiraConnector for local demo runs.
    Returns mock data instead of calling the Jira API.
    Logs what it would have done in a real deployment.
    """

    def get_registry_fields(self, jira_id: str) -> dict:
        logger.info(f"[MockJira] get_registry_fields({jira_id}) → returning mock registry")
        return MOCK_REGISTRY

    def create_content_bundle_task(self, jira_id: str, content_scope: list) -> str:
        task_key = f"{jira_id}-BUNDLE-MOCK"
        logger.info(f"[MockJira] Would create parent task: [{jira_id}] Content Bundle — {content_scope}")
        logger.info(f"[MockJira] → Mock task key: {task_key}")
        return task_key

    def create_approval_subtask(self, parent_task_key, jira_id, agent_id,
                                 content_category, document_type, department,
                                 draft_text, confidence_score, below_floor, context) -> str:
        subtask_key = f"{jira_id}-SUB-MOCK-1"
        flag = "🔴 LOW CONFIDENCE — " if below_floor else ""
        logger.info(
            f"[MockJira] Would create subtask: {flag}[{jira_id}] "
            f"{document_type} — {department} Review Required"
        )
        logger.info(f"[MockJira] Confidence score: {confidence_score:.2f}")
        logger.info(f"[MockJira] → Mock subtask key: {subtask_key}")
        logger.info(f"[MockJira] Draft preview (first 300 chars):\n{draft_text[:300]}...")
        return subtask_key

    def add_escalation_comment(self, subtask_key, approver_name, approver_dept):
        logger.info(f"[MockJira] Would add escalation comment to {subtask_key}")

    def create_lifecycle_review_tasks(self, **kwargs) -> list:
        logger.info(f"[MockJira] Would create lifecycle review tasks")
        return ["MOCK-LIFECYCLE-1"]

    def _extract_description(self, field) -> str:
        return str(field) if field else ""


def run_mock_pipeline():
    """
    Runs the full GACI pipeline with mock Jira connectivity.
    Real Claude API is called — you need ANTHROPIC_API_KEY in .env.
    """
    print("\n" + "=" * 60)
    print("GACI — Mock Pipeline Demo")
    print("=" * 60)
    print(f"Simulating Jira webhook: {MOCK_JIRA_ID} → {MOCK_NEW_STATUS}")
    print(f"Content scope: {MOCK_REGISTRY['content_scope']}")
    print("=" * 60 + "\n")

    # Patch the JiraConnector with our mock before importing the orchestrator
    import connectors.jira as jira_module
    jira_module.JiraConnector = MockJiraConnector

    from agents.orchestrator.agent import OrchestratorAgent, FeatureContext, CONTENT_GENERATION_STATUSES
    from agents.cs_documentation.agent import CSDocumentationAgent
    from governance.hitl.approval import HITLApprovalHandler

    # ── Step 1: Orchestrator receives trigger ─────────────────────────────────
    print("Step 1: Orchestrator — assembling feature context...")

    registry = MOCK_REGISTRY
    existing_blocks = []  # No existing content for this demo

    context = FeatureContext(
        jira_id=MOCK_JIRA_ID,
        jira_url=MOCK_APPROVER["jira_url"],
        product_name=registry["product_name"],
        feature_name=registry["feature_name"],
        feature_description=registry["description"],
        product_status=registry["product_status"],
        content_scope=registry["content_scope"],
        existing_content_blocks=existing_blocks,
        trigger_event=MOCK_NEW_STATUS,
    )

    parent_task_key = "PROD-1234-BUNDLE-MOCK"
    print(f"  → Feature context assembled for {MOCK_JIRA_ID}\n")

    # ── Step 2: CS Documentation Agent generates draft ────────────────────────
    print("Step 2: CS Documentation Agent — calling Claude...")
    print("  (This makes a real API call — may take 10–20 seconds)\n")

    agent = CSDocumentationAgent()
    result = agent.run(context=context, parent_task_key=parent_task_key)

    print(f"\n  → Draft generated")
    print(f"  → Confidence score: {result['confidence_score']:.2f}")
    print(f"  → Document type: {result['document_type']}")
    print(f"  → Subtask key: {result['subtask_key']}")
    print(f"  → Below confidence floor: {result['below_floor']}\n")

    # ── Step 3: Mock SME approval ─────────────────────────────────────────────
    print("Step 3: Simulating SME approval...")
    print(f"  Approver: {MOCK_APPROVER['name']} ({MOCK_APPROVER['department']})\n")

    hitl = HITLApprovalHandler()

    # Transfer the pending approval from the agent's HITL instance to ours
    # (in production this is handled by the webhook callback, not in-process)
    hitl._pending = agent.hitl._pending

    approval_result = hitl.handle_approval(
        subtask_key=result["subtask_key"],
        approved_by=MOCK_APPROVER["name"],
        approved_department=MOCK_APPROVER["department"],
        edited_content=None,  # No edits — approving as-is
        co_owner_smes=MOCK_APPROVER["co_owner_smes"],
        co_owner_departments=MOCK_APPROVER["co_owner_departments"],
        co_owner_subtask_keys=MOCK_APPROVER["co_owner_subtask_keys"],
        owner_sme=MOCK_APPROVER["owner_sme"],
        audience=MOCK_APPROVER["audience"],
        jira_url=MOCK_APPROVER["jira_url"],
    )

    # ── Step 4: Report outcome ────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("Pipeline Complete")
    print("=" * 60)
    print(f"Status:          {approval_result['status']}")
    print(f"Approval status: {approval_result['approval_status']}")
    print(f"File written to: {approval_result['file_path']}")
    print(f"Escalation sent: {approval_result.get('escalation_sent', False)}")
    print("\nOpen the file above to see the full structured output.")
    print("Import knowledge-repo/ into Obsidian to explore the repository structure.")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set.")
        print("Copy .env.example to .env and add your key.")
        sys.exit(1)

    run_mock_pipeline()

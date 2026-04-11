"""
Orchestrator Agent
==================
The single entry point for the GACI content pipeline.

Responsibilities:
- Receive trigger events from the Jira connector
- Parse the triggering event and extract feature metadata from the registry
- Determine content scope from the content_scope registry field
- Query the knowledge repository for existing content linked to this feature
- Spawn only the sub-agents declared in content_scope
- Create the parent Jira task and coordinate subtask creation per sub-agent
- For deprecation/sunset triggers: spawn lifecycle review tasks, not content generation

ACR Controls (Pillar 1 — Identity & Purpose Binding):
- Registered identity: orchestrator-agent
- Defined purpose: content pipeline coordination only
- Explicit scope: cannot access production systems, publish content, or modify registry

Reference: GACI Whitepaper v1.2, Section 2.2
"""

import logging
import os
from dataclasses import dataclass
from typing import Optional

from connectors.jira import JiraConnector
from connectors.knowledge_repo import KnowledgeRepoConnector
from agents.cs_documentation.agent import CSDocumentationAgent
# Stubs — uncomment as agents are implemented:
# from agents.pmm_enablement.agent import PMMEnablementAgent
# from agents.incident_management.agent import IncidentManagementAgent
# from agents.release_notes.agent import ReleaseNotesAgent

logger = logging.getLogger(__name__)

AGENT_MAP = {
    "CS": CSDocumentationAgent,
    # "PMM": PMMEnablementAgent,
    # "Incident": IncidentManagementAgent,
    # "Release Notes": ReleaseNotesAgent,
}

CONTENT_GENERATION_STATUSES = [
    s.strip() for s in os.getenv("JIRA_TRIGGER_STATUSES", "QA Ready,GA").split(",")
]
LIFECYCLE_REVIEW_STATUSES = ["Deprecated", "Sunset"]


@dataclass
class FeatureContext:
    """
    The context package assembled by the orchestrator and passed to each sub-agent.
    Contains everything a content agent needs to generate a draft.
    """
    jira_id: str
    jira_url: str
    product_name: str
    feature_name: str
    feature_description: str
    product_status: str
    content_scope: list[str]
    existing_content_blocks: list[dict]
    trigger_event: str
    deprecation_reason: Optional[str] = None
    successor_feature: Optional[str] = None
    sunset_date: Optional[str] = None


class OrchestratorAgent:
    """
    Coordinates the full GACI content pipeline from trigger to sub-agent spawn.
    Does not generate content itself.
    """

    AGENT_ID = "orchestrator-agent-v1.0"

    def __init__(self):
        self.jira = JiraConnector()
        self.repo = KnowledgeRepoConnector()

    def handle_trigger(self, jira_id: str, new_status: str) -> dict:
        """
        Main entry point. Called by the Jira webhook handler when a registry
        status change is detected.

        Returns a summary dict of actions taken.
        """
        logger.info(f"[{self.AGENT_ID}] Trigger received — {jira_id} → {new_status}")

        # 1. Fetch registry fields from Jira
        registry = self.jira.get_registry_fields(jira_id)
        if not registry:
            logger.error(f"[{self.AGENT_ID}] Could not retrieve registry fields for {jira_id}")
            return {"status": "error", "reason": "registry_fields_missing"}

        # 2. Route by trigger type
        if new_status in LIFECYCLE_REVIEW_STATUSES:
            return self._handle_lifecycle_review(jira_id, new_status, registry)

        if new_status in CONTENT_GENERATION_STATUSES:
            return self._handle_content_generation(jira_id, new_status, registry)

        logger.info(f"[{self.AGENT_ID}] Status '{new_status}' is not a GACI trigger — skipping")
        return {"status": "skipped", "reason": "non_trigger_status"}

    def _handle_content_generation(self, jira_id: str, trigger_status: str, registry: dict) -> dict:
        """
        Assembles feature context, spawns sub-agents for each declared content scope,
        and creates Jira approval tasks.
        """
        content_scope = registry.get("content_scope", [])
        if not content_scope or content_scope == ["None"]:
            logger.info(f"[{self.AGENT_ID}] content_scope is None for {jira_id} — no agents spawned")
            return {"status": "skipped", "reason": "content_scope_none"}

        # 3. Fetch existing content blocks from the repository
        existing_blocks = self.repo.get_blocks_by_jira_id(jira_id)

        # 4. Assemble context package
        context = FeatureContext(
            jira_id=jira_id,
            jira_url=f"{os.getenv('JIRA_BASE_URL')}/browse/{jira_id}",
            product_name=registry.get("product_name", ""),
            feature_name=registry.get("feature_name", ""),
            feature_description=registry.get("description", ""),
            product_status=registry.get("product_status", ""),
            content_scope=content_scope,
            existing_content_blocks=existing_blocks,
            trigger_event=trigger_status,
        )

        # 5. Create parent Jira task
        parent_task_key = self.jira.create_content_bundle_task(jira_id, content_scope)
        logger.info(f"[{self.AGENT_ID}] Created parent task {parent_task_key}")

        results = []

        # 6. Spawn one sub-agent per declared content scope
        for scope in content_scope:
            agent_class = AGENT_MAP.get(scope)
            if not agent_class:
                logger.warning(f"[{self.AGENT_ID}] No agent implemented for scope '{scope}' — skipping")
                results.append({"scope": scope, "status": "no_agent_implemented"})
                continue

            agent = agent_class()
            result = agent.run(context=context, parent_task_key=parent_task_key)
            results.append({"scope": scope, **result})
            logger.info(f"[{self.AGENT_ID}] {scope} agent completed — {result}")

        return {
            "status": "complete",
            "jira_id": jira_id,
            "parent_task": parent_task_key,
            "agents_spawned": results,
        }

    def _handle_lifecycle_review(self, jira_id: str, trigger_status: str, registry: dict) -> dict:
        """
        Handles Deprecated or Sunset triggers.
        Spawns lifecycle review tasks — does NOT generate new content.
        """
        logger.info(f"[{self.AGENT_ID}] Lifecycle review trigger for {jira_id} — {trigger_status}")

        existing_blocks = self.repo.get_blocks_by_jira_id(jira_id)
        if not existing_blocks:
            logger.info(f"[{self.AGENT_ID}] No existing content found for {jira_id} — nothing to review")
            return {"status": "complete", "reason": "no_existing_content"}

        # Create lifecycle review task in Jira for each affected content block
        review_tasks = self.jira.create_lifecycle_review_tasks(
            jira_id=jira_id,
            trigger_status=trigger_status,
            existing_blocks=existing_blocks,
            successor_feature=registry.get("successor_feature"),
            deprecation_reason=registry.get("deprecation_reason"),
        )

        return {
            "status": "complete",
            "trigger": trigger_status,
            "jira_id": jira_id,
            "review_tasks_created": review_tasks,
        }

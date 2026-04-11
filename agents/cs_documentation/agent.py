"""
CS Documentation Agent — MVP Agent
====================================
Generates Customer Service documentation drafts from feature context.
Routes drafts through the HITL approval gate as a Jira subtask.

This is the first fully implemented GACI agent.

ACR Controls (Pillar 2 — Behavioral Policy Enforcement):
- Cannot publish content — draft only
- Cannot access customer PII or production systems
- Confidence floor enforced: drafts below threshold are flagged RED in Jira
- Output format is policy-constrained to markdown

Reference: GACI Whitepaper v1.2, Section 2.3
"""

import logging
import os
import re
from datetime import datetime, timezone

import anthropic

from agents.cs_documentation.prompts import (
    SYSTEM_PROMPT,
    DRAFT_GENERATION_PROMPT,
    build_existing_content_section,
)
from connectors.jira import JiraConnector
from connectors.knowledge_repo import KnowledgeRepoConnector
from governance.hitl.approval import HITLApprovalHandler

logger = logging.getLogger(__name__)

CONFIDENCE_FLOOR = float(os.getenv("CS_AGENT_CONFIDENCE_FLOOR", "0.75"))


class CSDocumentationAgent:
    """
    Generates CS documentation drafts and creates Jira approval subtasks.
    Does not write to the knowledge repository — that is done by the
    HITLApprovalHandler when the SME approves.
    """

    AGENT_ID = "cs-doc-agent-v1.0"
    CONTENT_CATEGORY = "cs-documentation"
    DEPARTMENT = "customer-service"

    def __init__(self):
        self.client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
        self.jira = JiraConnector()
        self.repo = KnowledgeRepoConnector()
        self.hitl = HITLApprovalHandler()

    def run(self, context, parent_task_key: str) -> dict:
        """
        Full agent execution:
        1. Generate draft via Claude
        2. Parse confidence score from response
        3. Determine document type from context
        4. Create Jira subtask with draft inline
        5. Return result summary

        Does NOT write to the repository — that happens on SME approval.
        """
        logger.info(f"[{self.AGENT_ID}] Starting for {context.jira_id}")

        # 1. Build prompt with existing content context
        existing_section = build_existing_content_section(context.existing_content_blocks)

        prompt = DRAFT_GENERATION_PROMPT.format(
            jira_id=context.jira_id,
            product_name=context.product_name,
            feature_name=context.feature_name,
            feature_description=context.feature_description,
            product_status=context.product_status,
            trigger_event=context.trigger_event,
            existing_content_section=existing_section,
        )

        # 2. Call Claude
        logger.info(f"[{self.AGENT_ID}] Calling Claude for draft generation")
        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )

        draft_text = response.content[0].text

        # 3. Parse confidence score from draft
        confidence_score = self._parse_confidence_score(draft_text)
        below_floor = confidence_score < CONFIDENCE_FLOOR

        if below_floor:
            logger.warning(
                f"[{self.AGENT_ID}] Confidence {confidence_score} below floor {CONFIDENCE_FLOOR} "
                f"for {context.jira_id} — will flag RED in Jira"
            )

        # 4. Determine document type
        document_type = self._determine_document_type(context, draft_text)

        # 5. Create Jira subtask with draft inline
        subtask_key = self.jira.create_approval_subtask(
            parent_task_key=parent_task_key,
            jira_id=context.jira_id,
            agent_id=self.AGENT_ID,
            content_category=self.CONTENT_CATEGORY,
            document_type=document_type,
            department=self.DEPARTMENT,
            draft_text=draft_text,
            confidence_score=confidence_score,
            below_floor=below_floor,
            context=context,
        )

        logger.info(f"[{self.AGENT_ID}] Approval subtask created: {subtask_key}")

        # 6. Register pending approval with the HITL handler
        self.hitl.register_pending_approval(
            subtask_key=subtask_key,
            jira_id=context.jira_id,
            agent_id=self.AGENT_ID,
            content_category=self.CONTENT_CATEGORY,
            document_type=document_type,
            department=self.DEPARTMENT,
            product_name=context.product_name,
            feature_name=context.feature_name,
            draft_text=draft_text,
            confidence_score=confidence_score,
            existing_blocks=context.existing_content_blocks,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        return {
            "status": "draft_submitted",
            "subtask_key": subtask_key,
            "confidence_score": confidence_score,
            "below_floor": below_floor,
            "document_type": document_type,
        }

    def _parse_confidence_score(self, draft_text: str) -> float:
        """
        Extracts the self-assessed confidence score from the agent's response.
        Looks for the pattern: **Confidence Score**: 0.xx
        Falls back to 0.5 if not found.
        """
        match = re.search(r"\*\*Confidence Score\*\*:\s*([0-9.]+)", draft_text)
        if match:
            try:
                score = float(match.group(1))
                return max(0.0, min(1.0, score))  # clamp to [0, 1]
            except ValueError:
                pass

        logger.warning(f"[{self.AGENT_ID}] Could not parse confidence score — defaulting to 0.5")
        return 0.5

    def _determine_document_type(self, context, draft_text: str) -> str:
        """
        Determines the specific document type based on context.
        If existing content blocks exist, this is likely a delta/update.
        If no existing content, this is a new support guide.
        """
        if context.existing_content_blocks:
            return "troubleshooting-flow" if "troubleshoot" in draft_text.lower() else "faq-delta"
        return "support-guide"

"""
Human-in-the-Loop (HITL) Approval Handler
==========================================
Manages the full approval lifecycle for agent-generated content drafts.

Approval Model (agreed design):
- Single owner: one approval publishes the content immediately
- Co-owned documents: first approval publishes with approval_status=partial
  Second approval updates in-place, no version increment
- Escalation: when first co-owner approves, escalation comment added to
  the pending SME's Jira subtask
- Second escalation fires after ESCALATION_THRESHOLD_HOURS if still pending
- Content is NEVER published without at least one human approval

ACR Controls (Pillar 6 — Human Authority):
- No agent can call write_new_block directly — only this handler can
- All approvals are logged with timestamp, reviewer identity, and edits made
- Rejection creates a feedback record for future agent improvement

Reference: GACI Whitepaper v1.2, Section 2.4
"""

import logging
import os
from datetime import datetime, timezone
from typing import Optional

from connectors.knowledge_repo import KnowledgeRepoConnector
from connectors.jira import JiraConnector
from governance.acr.audit_log import AuditLog

logger = logging.getLogger(__name__)

ESCALATION_THRESHOLD_HOURS = int(os.getenv("ESCALATION_THRESHOLD_HOURS", "48"))


class HITLApprovalHandler:
    """
    Central authority for all content publication decisions.
    Only this class may call KnowledgeRepoConnector.write_new_block().
    """

    def __init__(self):
        self.repo = KnowledgeRepoConnector()
        self.jira = JiraConnector()
        self.audit = AuditLog()

        # In-memory pending approvals store
        # In production: replace with SQLite or a database
        self._pending: dict[str, dict] = {}

    def register_pending_approval(
        self,
        subtask_key: str,
        jira_id: str,
        agent_id: str,
        content_category: str,
        document_type: str,
        department: str,
        product_name: str,
        feature_name: str,
        draft_text: str,
        confidence_score: float,
        existing_blocks: list[dict],
        created_at: str,
    ) -> None:
        """
        Registers a pending approval after an agent creates a Jira subtask.
        Stores the draft context so it can be retrieved when the SME responds.
        """
        self._pending[subtask_key] = {
            "subtask_key": subtask_key,
            "jira_id": jira_id,
            "agent_id": agent_id,
            "content_category": content_category,
            "document_type": document_type,
            "department": department,
            "product_name": product_name,
            "feature_name": feature_name,
            "draft_text": draft_text,
            "confidence_score": confidence_score,
            "existing_blocks": existing_blocks,
            "created_at": created_at,
            "status": "pending",
        }
        logger.info(f"[HITL] Registered pending approval for subtask {subtask_key}")

    def handle_approval(
        self,
        subtask_key: str,
        approved_by: str,
        approved_department: str,
        edited_content: Optional[str] = None,
        co_owner_smes: Optional[list[str]] = None,
        co_owner_departments: Optional[list[str]] = None,
        co_owner_subtask_keys: Optional[list[str]] = None,
        owner_sme: Optional[str] = None,
        audience: Optional[list[str]] = None,
        jira_url: Optional[str] = None,
    ) -> dict:
        """
        Called when an SME approves a Jira subtask.

        If this is the first (and only required) approval: publishes immediately.
        If co-owners exist and this is the first approval: publishes with partial status,
        fires escalation to remaining co-owner subtasks.
        If this is a second approval on a partial document: updates in-place to full approval.
        """
        pending = self._pending.get(subtask_key)
        if not pending:
            logger.error(f"[HITL] No pending approval found for subtask {subtask_key}")
            return {"status": "error", "reason": "subtask_not_found"}

        now = datetime.now(timezone.utc).isoformat()
        content_to_write = edited_content or pending["draft_text"]
        jira_id = pending["jira_id"]

        # Check if this is a second approval on an already-published partial document
        existing_partial = self._find_partial_block(jira_id, pending["content_category"])
        if existing_partial:
            return self._complete_partial_approval(
                file_path=existing_partial,
                approver=approved_by,
                approver_dept=approved_department,
                approved_at=now,
                subtask_key=subtask_key,
                pending=pending,
            )

        # First approval — determine if co-owners exist
        has_co_owners = bool(co_owner_smes and co_owner_departments)
        pending_approval_from = co_owner_smes[0] if has_co_owners else None
        pending_approval_dept = co_owner_departments[0] if has_co_owners else None

        # Write to repository
        file_path = self.repo.write_new_block(
            jira_id=jira_id,
            jira_url=jira_url or f"{os.getenv('JIRA_BASE_URL')}/browse/{jira_id}",
            product=pending["product_name"],
            feature=pending["feature_name"],
            owner_department=pending["department"],
            owner_sme=owner_sme or approved_by,
            co_owner_departments=co_owner_departments or [],
            co_owner_smes=co_owner_smes or [],
            audience=audience or [],
            document_type=pending["document_type"],
            content_category=pending["content_category"],
            content=content_to_write,
            confidence_score=pending["confidence_score"],
            agent_id=pending["agent_id"],
            approved_by=[approved_by],
            approved_at=[now],
            approved_departments=[approved_department],
            pending_approval_from=pending_approval_from,
            pending_approval_department=pending_approval_dept,
        )

        logger.info(f"[HITL] Content published: {file_path}")

        # Fire escalation to co-owner subtasks if partial approval
        if has_co_owners and co_owner_subtask_keys:
            for co_subtask in co_owner_subtask_keys:
                self.jira.add_escalation_comment(
                    subtask_key=co_subtask,
                    approver_name=approved_by,
                    approver_dept=approved_department,
                )
                logger.info(f"[HITL] Escalation comment added to {co_subtask}")

        # Audit log
        self.audit.log_approval(
            subtask_key=subtask_key,
            jira_id=jira_id,
            approved_by=approved_by,
            approved_department=approved_department,
            approval_status="partial" if has_co_owners else "full",
            file_path=str(file_path),
            was_edited=edited_content is not None,
            timestamp=now,
        )

        # Clean up pending record
        self._pending[subtask_key]["status"] = "approved"

        return {
            "status": "published",
            "approval_status": "partial" if has_co_owners else "full",
            "file_path": str(file_path),
            "escalation_sent": has_co_owners,
        }

    def handle_rejection(self, subtask_key: str, rejected_by: str, reason: str) -> dict:
        """
        Called when an SME rejects a Jira subtask.
        Creates a feedback record — does NOT publish content.
        Content remains in under-review state (not written to repository).
        """
        pending = self._pending.get(subtask_key)
        if not pending:
            return {"status": "error", "reason": "subtask_not_found"}

        now = datetime.now(timezone.utc).isoformat()

        self.audit.log_rejection(
            subtask_key=subtask_key,
            jira_id=pending["jira_id"],
            rejected_by=rejected_by,
            reason=reason,
            agent_id=pending["agent_id"],
            confidence_score=pending["confidence_score"],
            timestamp=now,
        )

        self._pending[subtask_key]["status"] = "rejected"

        logger.info(f"[HITL] Rejection recorded for {subtask_key} — reason: {reason}")
        return {"status": "rejected", "feedback_recorded": True}

    def _complete_partial_approval(
        self,
        file_path: str,
        approver: str,
        approver_dept: str,
        approved_at: str,
        subtask_key: str,
        pending: dict,
    ) -> dict:
        """
        Handles the second approval on a co-owned document.
        Updates the file in-place — no new version, no re-write.
        """
        self.repo.update_approval_status(
            file_path=file_path,
            new_approver=approver,
            new_approver_dept=approver_dept,
            approved_at=approved_at,
        )

        self.audit.log_approval(
            subtask_key=subtask_key,
            jira_id=pending["jira_id"],
            approved_by=approver,
            approved_department=approver_dept,
            approval_status="full",
            file_path=file_path,
            was_edited=False,
            timestamp=approved_at,
        )

        self._pending[subtask_key]["status"] = "approved"

        logger.info(f"[HITL] Partial → full approval completed for {file_path}")
        return {
            "status": "approval_completed",
            "approval_status": "full",
            "file_path": file_path,
        }

    def _find_partial_block(self, jira_id: str, content_category: str) -> Optional[str]:
        """
        Checks if a partial-approval block already exists for this jira_id
        and content_category. Returns the file path if found, None otherwise.
        """
        blocks = self.repo.get_blocks_by_jira_id(jira_id)
        for block in blocks:
            if (
                block.get("content_category") == content_category
                and block.get("approval_status") == "partial"
                and block.get("lifecycle_state") == "active"
            ):
                return block.get("file_path")
        return None

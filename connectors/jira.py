"""
Jira Connector
==============
Handles all communication with the Jira API:
- Reading registry fields from epics/features
- Creating parent content bundle tasks
- Creating per-agent approval subtasks
- Adding escalation comments to pending subtasks
- Creating lifecycle review tasks

Reference: GACI Whitepaper v1.2, Sections 2.2 and 2.4
"""

import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

JIRA_BASE_URL = os.getenv("JIRA_BASE_URL", "")
JIRA_USER_EMAIL = os.getenv("JIRA_USER_EMAIL", "")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN", "")
JIRA_PROJECT_KEY = os.getenv("JIRA_PROJECT_KEY", "PROD")

# Registry field IDs — configured per deployment in .env
FIELD_PRODUCT_STATUS = os.getenv("JIRA_FIELD_PRODUCT_STATUS", "customfield_10001")
FIELD_CONTENT_SCOPE = os.getenv("JIRA_FIELD_CONTENT_SCOPE", "customfield_10002")
FIELD_DEPRECATION_REASON = os.getenv("JIRA_FIELD_DEPRECATION_REASON", "customfield_10003")
FIELD_SUCCESSOR_FEATURE = os.getenv("JIRA_FIELD_SUCCESSOR_FEATURE", "customfield_10004")
FIELD_SUNSET_DATE = os.getenv("JIRA_FIELD_SUNSET_DATE", "customfield_10005")

CONFIDENCE_FLOOR = float(os.getenv("CS_AGENT_CONFIDENCE_FLOOR", "0.75"))


def _auth() -> tuple[str, str]:
    return (JIRA_USER_EMAIL, JIRA_API_TOKEN)


def _headers() -> dict:
    return {"Accept": "application/json", "Content-Type": "application/json"}


class JiraConnector:

    def get_registry_fields(self, jira_id: str) -> Optional[dict]:
        """
        Fetches the GACI registry fields from a Jira issue.
        Also extracts product name, feature name, and description from standard fields.
        Returns None if the issue cannot be retrieved.
        """
        url = f"{JIRA_BASE_URL}/rest/api/3/issue/{jira_id}"
        try:
            response = httpx.get(url, auth=_auth(), headers=_headers(), timeout=10.0)
            response.raise_for_status()
        except httpx.HTTPError as e:
            logger.error(f"[JiraConnector] Failed to fetch {jira_id}: {e}")
            return None

        fields = response.json().get("fields", {})

        # Parse content_scope — Jira returns multi-select as list of dicts
        raw_scope = fields.get(FIELD_CONTENT_SCOPE, []) or []
        content_scope = [item["value"] for item in raw_scope if isinstance(item, dict)]

        return {
            "jira_id": jira_id,
            "product_name": fields.get("summary", "").split("—")[0].strip(),
            "feature_name": fields.get("summary", ""),
            "description": self._extract_description(fields.get("description")),
            "product_status": (fields.get(FIELD_PRODUCT_STATUS) or {}).get("value", ""),
            "content_scope": content_scope,
            "deprecation_reason": fields.get(FIELD_DEPRECATION_REASON, ""),
            "successor_feature": fields.get(FIELD_SUCCESSOR_FEATURE, ""),
            "sunset_date": fields.get(FIELD_SUNSET_DATE, ""),
        }

    def create_content_bundle_task(self, jira_id: str, content_scope: list[str]) -> str:
        """
        Creates the parent Jira task:
        '[JIRA-ID] Content Bundle — Pending Review'

        Returns the new task key (e.g. PROD-1299).
        """
        scope_display = ", ".join(content_scope)
        summary = f"[{jira_id}] Content Bundle — Pending Review ({scope_display})"

        url = f"{JIRA_BASE_URL}/rest/api/3/issue"
        payload = {
            "fields": {
                "project": {"key": JIRA_PROJECT_KEY},
                "summary": summary,
                "issuetype": {"name": "Task"},
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [{
                        "type": "paragraph",
                        "content": [{
                            "type": "text",
                            "text": (
                                f"GACI content bundle triggered by {jira_id}. "
                                f"Agents spawned for: {scope_display}. "
                                "This task cannot be closed until all subtasks are resolved."
                            ),
                        }],
                    }],
                },
                "parent": {"key": jira_id},
            }
        }

        response = httpx.post(url, auth=_auth(), headers=_headers(), json=payload, timeout=10.0)
        response.raise_for_status()
        return response.json()["key"]

    def create_approval_subtask(
        self,
        parent_task_key: str,
        jira_id: str,
        agent_id: str,
        content_category: str,
        document_type: str,
        department: str,
        draft_text: str,
        confidence_score: float,
        below_floor: bool,
        context,
    ) -> str:
        """
        Creates a Jira subtask for SME review containing the agent draft inline.
        Flags the task RED if confidence is below floor.
        Returns the subtask key.
        """
        confidence_flag = "🔴 LOW CONFIDENCE — " if below_floor else ""
        summary = (
            f"{confidence_flag}[{jira_id}] {document_type.replace('-', ' ').title()} "
            f"— {department.replace('-', ' ').title()} Review Required"
        )

        # Build the approval package description
        description_text = self._build_approval_package(
            jira_id=jira_id,
            context=context,
            document_type=document_type,
            department=department,
            draft_text=draft_text,
            confidence_score=confidence_score,
            below_floor=below_floor,
            agent_id=agent_id,
        )

        url = f"{JIRA_BASE_URL}/rest/api/3/issue"
        payload = {
            "fields": {
                "project": {"key": JIRA_PROJECT_KEY},
                "summary": summary,
                "issuetype": {"name": "Subtask"},
                "parent": {"key": parent_task_key},
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [{
                        "type": "paragraph",
                        "content": [{"type": "text", "text": description_text}],
                    }],
                },
            }
        }

        response = httpx.post(url, auth=_auth(), headers=_headers(), json=payload, timeout=10.0)
        response.raise_for_status()
        return response.json()["key"]

    def add_escalation_comment(self, subtask_key: str, approver_name: str, approver_dept: str) -> None:
        """
        Adds an escalation comment to a pending co-owner subtask after the
        first approval has already published the content.
        """
        comment = (
            f"⚠️ ESCALATION — This document is now LIVE with partial approval.\n\n"
            f"Approved by: {approver_name} ({approver_dept})\n"
            f"Your review as co-owner is still outstanding. "
            f"The document will reflect partial approval status until you complete your review.\n\n"
            f"Please review and Approve / Edit / Reject this subtask."
        )
        url = f"{JIRA_BASE_URL}/rest/api/3/issue/{subtask_key}/comment"
        payload = {
            "body": {
                "type": "doc",
                "version": 1,
                "content": [{"type": "paragraph", "content": [{"type": "text", "text": comment}]}],
            }
        }
        response = httpx.post(url, auth=_auth(), headers=_headers(), json=payload, timeout=10.0)
        response.raise_for_status()
        logger.info(f"[JiraConnector] Escalation comment added to {subtask_key}")

    def create_lifecycle_review_tasks(
        self,
        jira_id: str,
        trigger_status: str,
        existing_blocks: list[dict],
        successor_feature: Optional[str],
        deprecation_reason: Optional[str],
    ) -> list[str]:
        """
        Creates lifecycle review tasks for each content block affected by a
        Deprecated or Sunset trigger. Returns list of created task keys.
        """
        created = []
        for block in existing_blocks:
            summary = (
                f"[LIFECYCLE] [{jira_id}] {trigger_status} — "
                f"{block.get('document_type', 'document')} review required"
            )
            action = "REDIRECT to successor" if successor_feature else "ARCHIVE (no successor)"
            description = (
                f"Feature {jira_id} has been marked {trigger_status}.\n\n"
                f"Deprecation reason: {deprecation_reason or 'Not provided'}\n"
                f"Successor feature: {successor_feature or 'None — archive action required'}\n"
                f"Recommended action: {action}\n\n"
                f"Affected content block:\n"
                f"  - Type: {block.get('document_type')}\n"
                f"  - Version: {block.get('version')}\n"
                f"  - Approved by: {block.get('approved_by')}\n"
                f"  - File: {block.get('file_path')}\n\n"
                f"Please confirm the content lifecycle action to proceed."
            )

            url = f"{JIRA_BASE_URL}/rest/api/3/issue"
            payload = {
                "fields": {
                    "project": {"key": JIRA_PROJECT_KEY},
                    "summary": summary,
                    "issuetype": {"name": "Task"},
                    "parent": {"key": jira_id},
                    "description": {
                        "type": "doc",
                        "version": 1,
                        "content": [{"type": "paragraph", "content": [{"type": "text", "text": description}]}],
                    },
                }
            }
            response = httpx.post(url, auth=_auth(), headers=_headers(), json=payload, timeout=10.0)
            response.raise_for_status()
            created.append(response.json()["key"])

        return created

    def _build_approval_package(
        self, jira_id, context, document_type, department,
        draft_text, confidence_score, below_floor, agent_id
    ) -> str:
        """Formats the SME approval package as readable text for the Jira subtask body."""
        confidence_warning = (
            "\n🔴 CONFIDENCE BELOW THRESHOLD — Review this draft carefully before approving.\n"
            if below_floor else ""
        )
        existing = context.existing_content_blocks
        existing_summary = (
            "\n".join(
                f"  - {b.get('document_type')} v{b.get('version')} "
                f"(approved by {b.get('approved_by')} on {b.get('approved_at')})"
                for b in existing
            ) if existing else "  None — this is new content."
        )

        return (
            f"GACI Content Review — {document_type.replace('-', ' ').title()}\n"
            f"{'=' * 60}\n\n"
            f"Feature: {context.feature_name}\n"
            f"Jira ID: {jira_id} ({context.jira_url})\n"
            f"Product: {context.product_name}\n"
            f"Product Status: {context.product_status}\n"
            f"Owning Department: {department}\n"
            f"Generated by: {agent_id}\n"
            f"{confidence_warning}\n"
            f"Confidence Score: {confidence_score:.2f}\n\n"
            f"Existing content under your purview:\n{existing_summary}\n\n"
            f"{'─' * 60}\n"
            f"DRAFT (tracked changes where applicable):\n\n"
            f"{draft_text}\n\n"
            f"{'─' * 60}\n"
            f"Required action: Approve / Edit / Reject\n"
            f"Closing this subtask will trigger the repository write."
        )

    def _extract_description(self, description_field) -> str:
        """Extracts plain text from Jira's Atlassian Document Format description field."""
        if not description_field:
            return ""
        if isinstance(description_field, str):
            return description_field
        # ADF format — walk the content tree
        texts = []
        for block in description_field.get("content", []):
            for inline in block.get("content", []):
                if inline.get("type") == "text":
                    texts.append(inline.get("text", ""))
        return " ".join(texts)

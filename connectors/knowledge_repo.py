"""
Knowledge Repository Connector
================================
Reads from and writes to the structured markdown knowledge repository.
This is the interface layer between the agents and the file system.

All writes go through the HITLApprovalHandler — this connector handles
the raw file operations only.

File naming convention:
  {jira_id}_{product}_{feature}_{department}_{doc-type}_v{version}.md

Folder structure:
  knowledge-repo/{org}/{product}/{content-category}/{jira-id}/{lifecycle-state}/

Reference: GACI Whitepaper v1.2, Section 3
"""

import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import frontmatter

logger = logging.getLogger(__name__)

REPO_PATH = Path(os.getenv("KNOWLEDGE_REPO_PATH", "./knowledge-repo"))
ORG_NAME = os.getenv("ORG_NAME", "example-org")


def _slugify(text: str) -> str:
    """Converts text to a filename-safe slug."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


class KnowledgeRepoConnector:

    def get_blocks_by_jira_id(self, jira_id: str) -> list[dict]:
        """
        Finds all content blocks in the repository linked to a given Jira ID.
        Searches across all content categories and lifecycle states.
        Returns a list of metadata dicts (frontmatter + file_path).
        """
        results = []
        org_path = REPO_PATH / ORG_NAME

        if not org_path.exists():
            return results

        # Walk all markdown files in the org
        for md_file in org_path.rglob("*.md"):
            try:
                post = frontmatter.load(str(md_file))
                if post.metadata.get("jira_id") == jira_id:
                    block = dict(post.metadata)
                    block["file_path"] = str(md_file)
                    block["content_preview"] = post.content[:500]
                    results.append(block)
            except Exception as e:
                logger.warning(f"[KnowledgeRepoConnector] Could not parse {md_file}: {e}")

        logger.info(f"[KnowledgeRepoConnector] Found {len(results)} blocks for {jira_id}")
        return results

    def write_new_block(
        self,
        jira_id: str,
        jira_url: str,
        product: str,
        feature: str,
        owner_department: str,
        owner_sme: str,
        co_owner_departments: list[str],
        co_owner_smes: list[str],
        audience: list[str],
        document_type: str,
        content_category: str,
        content: str,
        confidence_score: float,
        agent_id: str,
        approved_by: list[str],
        approved_at: list[str],
        approved_departments: list[str],
        pending_approval_from: Optional[str] = None,
        pending_approval_department: Optional[str] = None,
        escalation_sent: bool = False,
        escalation_sent_at: Optional[str] = None,
        escalation_jira_subtask: Optional[str] = None,
    ) -> Path:
        """
        Writes a new approved content block to the repository.
        Determines version by incrementing the highest existing version for this jira_id + content_category.
        Returns the path of the written file.
        """
        version = self._next_version(jira_id, content_category)
        approval_status = "partial" if pending_approval_from else "full"

        product_slug = _slugify(product)
        feature_slug = _slugify(feature)
        dept_slug = _slugify(owner_department)
        doc_slug = _slugify(document_type)
        lifecycle_state = "active"

        # Build file path
        folder = (
            REPO_PATH / ORG_NAME / product_slug / content_category
            / jira_id / lifecycle_state
        )
        folder.mkdir(parents=True, exist_ok=True)

        filename = f"{jira_id}_{product_slug}_{feature_slug}_{dept_slug}_{doc_slug}_v{version}.md"
        file_path = folder / filename

        # Build approval notice for document body
        approval_notice = self._build_approval_notice(
            approved_by=approved_by,
            approved_departments=approved_departments,
            approved_at=approved_at,
            pending_approval_from=pending_approval_from,
            pending_approval_department=pending_approval_department,
        )

        # Build frontmatter
        metadata = {
            "jira_id": jira_id,
            "jira_url": jira_url,
            "product": product,
            "feature": feature,
            "owner_department": owner_department,
            "owner_sme": owner_sme,
            "co_owner_departments": co_owner_departments,
            "co_owner_smes": co_owner_smes,
            "audience": audience,
            "document_type": document_type,
            "content_category": content_category,
            "version": version,
            "lifecycle_state": lifecycle_state,
            "approval_status": approval_status,
            "approvals_required": 1 + len(co_owner_departments),
            "approved_by": approved_by,
            "approved_at": approved_at,
            "approved_departments": approved_departments,
            "pending_approval_from": pending_approval_from,
            "pending_approval_department": pending_approval_department,
            "pending_since": approved_at[-1] if pending_approval_from else None,
            "escalation_sent": escalation_sent,
            "escalation_sent_at": escalation_sent_at,
            "escalation_jira_subtask": escalation_jira_subtask,
            "confidence_score": round(confidence_score, 2),
            "agent_id": agent_id,
            "tags": [
                product_slug, feature_slug, jira_id,
                dept_slug, doc_slug, lifecycle_state,
                approval_status,
            ],
        }

        post = frontmatter.Post(content=f"{approval_notice}\n\n{content}", **metadata)
        with open(file_path, "wb") as f:
            frontmatter.dump(post, f)

        logger.info(f"[KnowledgeRepoConnector] Written: {file_path}")
        return file_path

    def update_approval_status(self, file_path: str, new_approver: str, new_approver_dept: str, approved_at: str) -> None:
        """
        Updates an existing file in-place when a co-owner approves.
        Moves approval_status from 'partial' to 'full'.
        Clears pending_approval fields.
        Does NOT change the version number — approval state is not a content change.
        """
        post = frontmatter.load(file_path)

        post.metadata["approved_by"] = post.metadata.get("approved_by", []) + [new_approver]
        post.metadata["approved_at"] = post.metadata.get("approved_at", []) + [approved_at]
        post.metadata["approved_departments"] = (
            post.metadata.get("approved_departments", []) + [new_approver_dept]
        )
        post.metadata["approval_status"] = "full"
        post.metadata["pending_approval_from"] = None
        post.metadata["pending_approval_department"] = None
        post.metadata["pending_since"] = None

        # Rebuild tags without 'partial', add 'full'
        tags = [t for t in post.metadata.get("tags", []) if t != "partial"]
        if "full" not in tags:
            tags.append("full")
        post.metadata["tags"] = tags

        # Replace the approval notice in the document body
        new_notice = self._build_approval_notice(
            approved_by=post.metadata["approved_by"],
            approved_departments=post.metadata["approved_departments"],
            approved_at=post.metadata["approved_at"],
            pending_approval_from=None,
            pending_approval_department=None,
        )

        # Replace the existing notice block (everything before the first ---)
        body = post.content
        if "\n\n---\n" in body:
            body = new_notice + "\n\n---\n" + body.split("\n\n---\n", 1)[1]
        else:
            body = new_notice + "\n\n" + body
        post.content = body

        with open(file_path, "wb") as f:
            frontmatter.dump(post, f)

        logger.info(f"[KnowledgeRepoConnector] Approval status updated to full: {file_path}")

    def move_to_lifecycle_state(self, file_path: str, new_state: str) -> Path:
        """
        Moves a file to a different lifecycle state folder (e.g. active → archived).
        Updates the lifecycle_state frontmatter field.
        Returns the new file path.
        """
        src = Path(file_path)
        # Replace the lifecycle state folder segment in the path
        parts = src.parts
        state_idx = parts.index(src.parent.name)  # current state folder
        new_parts = parts[:state_idx] + (new_state,) + parts[state_idx + 1:]
        dest_dir = Path(*new_parts[:-1])
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / src.name

        post = frontmatter.load(str(src))
        post.metadata["lifecycle_state"] = new_state
        with open(dest, "wb") as f:
            frontmatter.dump(post, f)

        src.unlink()
        logger.info(f"[KnowledgeRepoConnector] Moved {src.name} → {new_state}/")
        return dest

    def _next_version(self, jira_id: str, content_category: str) -> int:
        """
        Determines the next version number for a jira_id + content_category combination
        by finding the highest existing version across all lifecycle states.
        """
        highest = 0
        org_path = REPO_PATH / ORG_NAME
        if not org_path.exists():
            return 1

        pattern = re.compile(rf"^{re.escape(jira_id)}_.*_v(\d+)\.md$")
        for md_file in org_path.rglob("*.md"):
            if content_category in str(md_file):
                match = pattern.match(md_file.name)
                if match:
                    highest = max(highest, int(match.group(1)))

        return highest + 1

    def _build_approval_notice(
        self,
        approved_by: list[str],
        approved_departments: list[str],
        approved_at: list[str],
        pending_approval_from: Optional[str],
        pending_approval_department: Optional[str],
    ) -> str:
        """Generates the visible approval status notice block for the document body."""
        if pending_approval_from:
            status = "**Approval Status — Partial**"
            pending_line = f"Pending: {pending_approval_from}, {pending_approval_department} (escalation sent)"
        else:
            status = "**Approval Status — Full**"
            pending_line = ""

        approver_lines = "\n".join(
            f"Approved by: {name}, {dept} — {at}"
            for name, dept, at in zip(approved_by, approved_departments, approved_at)
        )

        lines = [f"> {status}", f"> {approver_lines}"]
        if pending_line:
            lines.append(f"> {pending_line}")
        lines.append("> This document is active and authoritative.")

        return "\n".join(lines)

"""
ACR Audit Log — Pillar 4: Execution Observability
==================================================
Logs every approval, rejection, and agent execution event.
Uses SQLite for zero-infrastructure local deployment.

In production: replace with a managed database.

ACR Framework™ Pillar 4 requires:
- Full structured trace per execution
- Every approval logged with: timestamp, reviewer identity, edits made
- Every rejection logged with: timestamp, reviewer, reason, agent ID, confidence score

Reference: GACI Whitepaper v1.2, Section 5
"""

import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = os.getenv("AUDIT_DB_PATH", "./audit.db")


class AuditLog:

    def __init__(self):
        self._init_db()

    def log_approval(
        self,
        subtask_key: str,
        jira_id: str,
        approved_by: str,
        approved_department: str,
        approval_status: str,
        file_path: str,
        was_edited: bool,
        timestamp: str,
    ) -> None:
        self._insert("approval", {
            "subtask_key": subtask_key,
            "jira_id": jira_id,
            "actor": approved_by,
            "actor_department": approved_department,
            "approval_status": approval_status,
            "file_path": file_path,
            "was_edited": int(was_edited),
            "timestamp": timestamp,
        })
        logger.info(f"[AuditLog] Approval logged — {subtask_key} by {approved_by}")

    def log_rejection(
        self,
        subtask_key: str,
        jira_id: str,
        rejected_by: str,
        reason: str,
        agent_id: str,
        confidence_score: float,
        timestamp: str,
    ) -> None:
        self._insert("rejection", {
            "subtask_key": subtask_key,
            "jira_id": jira_id,
            "actor": rejected_by,
            "reason": reason,
            "agent_id": agent_id,
            "confidence_score": confidence_score,
            "timestamp": timestamp,
        })
        logger.info(f"[AuditLog] Rejection logged — {subtask_key} by {rejected_by}")

    def log_agent_execution(
        self,
        agent_id: str,
        jira_id: str,
        trigger_event: str,
        outcome: str,
        confidence_score: float,
        timestamp: str,
    ) -> None:
        self._insert("agent_execution", {
            "agent_id": agent_id,
            "jira_id": jira_id,
            "trigger_event": trigger_event,
            "outcome": outcome,
            "confidence_score": confidence_score,
            "timestamp": timestamp,
        })

    def _init_db(self) -> None:
        Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                subtask_key TEXT,
                jira_id TEXT,
                agent_id TEXT,
                actor TEXT,
                actor_department TEXT,
                approval_status TEXT,
                file_path TEXT,
                was_edited INTEGER,
                reason TEXT,
                trigger_event TEXT,
                outcome TEXT,
                confidence_score REAL,
                timestamp TEXT NOT NULL,
                logged_at TEXT NOT NULL
            )
        """)

        conn.commit()
        conn.close()

    def _insert(self, event_type: str, data: dict) -> None:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        data["event_type"] = event_type
        data["logged_at"] = datetime.now(timezone.utc).isoformat()

        columns = ", ".join(data.keys())
        placeholders = ", ".join("?" * len(data))
        cursor.execute(
            f"INSERT INTO audit_events ({columns}) VALUES ({placeholders})",
            list(data.values()),
        )
        conn.commit()
        conn.close()

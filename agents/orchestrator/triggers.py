"""
Webhook Trigger Handler
=======================
FastAPI application that receives Jira webhook events and routes them
to the OrchestratorAgent.

Jira sends a POST request to /webhook/jira whenever a watched issue
changes status. This module validates the payload and calls the orchestrator.

Reference: GACI Whitepaper v1.2, Section 2.2 — Trigger Events
"""

import hashlib
import hmac
import logging
import os

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from agents.orchestrator.agent import OrchestratorAgent

logger = logging.getLogger(__name__)
app = FastAPI(title="GACI Webhook Receiver", version="1.0.0")

orchestrator = OrchestratorAgent()


def _validate_signature(payload: bytes, signature: str) -> bool:
    """
    Validates the Jira webhook signature against WEBHOOK_SECRET.
    Skip validation if WEBHOOK_SECRET is not set (development only).
    """
    secret = os.getenv("WEBHOOK_SECRET")
    if not secret:
        logger.warning("WEBHOOK_SECRET not set — skipping signature validation (dev mode)")
        return True

    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.removeprefix("sha256="))


@app.post("/webhook/jira")
async def jira_webhook(
    request: Request,
    x_hub_signature_256: str = Header(default=""),
):
    """
    Receives Jira status change webhooks and routes to the orchestrator.

    Expected payload shape:
    {
        "issue": {
            "key": "PROD-1234",
            "fields": { ... }
        },
        "changelog": {
            "items": [
                {
                    "field": "status",
                    "fromString": "In Progress",
                    "toString": "QA Ready"
                }
            ]
        }
    }
    """
    payload = await request.body()

    if not _validate_signature(payload, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    data = await request.json()

    # Extract the status change from the changelog
    changelog_items = data.get("changelog", {}).get("items", [])
    status_change = next(
        (item for item in changelog_items if item.get("field") == "status"), None
    )

    if not status_change:
        return JSONResponse({"status": "ignored", "reason": "no_status_change_in_payload"})

    jira_id = data.get("issue", {}).get("key")
    new_status = status_change.get("toString")

    if not jira_id or not new_status:
        raise HTTPException(status_code=400, detail="Missing issue key or status in payload")

    logger.info(f"Webhook received — {jira_id} → {new_status}")

    result = orchestrator.handle_trigger(jira_id=jira_id, new_status=new_status)

    return JSONResponse(result)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "gaci-webhook-receiver"}

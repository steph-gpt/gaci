"""
ACR Framework™ — Pillar 1: Identity & Purpose Binding
======================================================
Agent identity registry. Every agent in the GACI workforce has a registered
identity, named owner, defined purpose, and explicit scope.

This file is a placeholder pending consultation with the ACR Framework™ creator.
The structure reflects the whitepaper specification.

Reference: GACI Whitepaper v1.2, Section 5 — ACR Pillar 1
"""

# Agent identity registry
# In production: load from a secure configuration store, not a hardcoded dict

AGENT_REGISTRY = {
    "orchestrator-agent-v1.0": {
        "purpose": "Content pipeline coordination only",
        "scope": [
            "Read Jira registry fields",
            "Create Jira tasks and subtasks",
            "Spawn declared sub-agents",
            "Query knowledge repository for existing blocks",
        ],
        "explicitly_prohibited": [
            "Access production systems",
            "Publish or modify content",
            "Modify the Jira registry",
            "Access customer PII",
        ],
    },
    "cs-doc-agent-v1.0": {
        "purpose": "Generate Customer Service documentation drafts",
        "scope": [
            "Generate markdown content drafts using Claude",
            "Self-assess confidence score",
            "Create Jira approval subtasks",
        ],
        "explicitly_prohibited": [
            "Publish content without human approval",
            "Access customer PII",
            "Access production systems",
            "Write directly to the knowledge repository",
        ],
    },
    "incident-agent-v1.0": {
        "purpose": "Generate Incident Management runbook drafts",
        "scope": [
            "Generate runbook and SOP drafts using Claude",
            "Self-assess confidence score (floor: 0.90)",
            "Create Jira approval subtasks",
        ],
        "explicitly_prohibited": [
            "Publish content without human approval",
            "Access customer PII",
            "Access production systems",
            "Write directly to the knowledge repository",
        ],
        "additional_constraints": [
            "Confidence floor is 0.90 — higher than other agents due to operational risk",
            "Mandatory SME sign-off before any runbook change is published",
        ],
    },
    "variance-detection-agent-v1.0": {
        "purpose": "Detect variance between practitioner documentation and approved content",
        "scope": [
            "Read practitioner-authored fields in case management systems",
            "Compare patterns against approved repository content",
            "Create variance review tasks in Jira",
        ],
        "explicitly_prohibited": [
            "Read customer-authored fields",
            "Access customer PII",
            "Modify the knowledge repository",
            "Write to case notes",
            "Update documentation autonomously",
        ],
    },
}


def get_agent_identity(agent_id: str) -> dict:
    """Returns the registered identity for a given agent ID."""
    identity = AGENT_REGISTRY.get(agent_id)
    if not identity:
        raise ValueError(f"Agent '{agent_id}' is not registered in the GACI identity registry.")
    return identity


def assert_agent_permitted(agent_id: str, action: str) -> None:
    """
    Raises PermissionError if the action is in the agent's prohibited list.
    Call this at the start of any sensitive operation.
    """
    identity = get_agent_identity(agent_id)
    for prohibited in identity.get("explicitly_prohibited", []):
        if action.lower() in prohibited.lower():
            raise PermissionError(
                f"Agent '{agent_id}' is explicitly prohibited from: {prohibited}. "
                f"Attempted action: {action}"
            )

---
jira_id: PROD-1234
jira_url: https://example-org.atlassian.net/browse/PROD-1234
product: sentinelone
feature: v8-upgrade
owner_department: incident-management
owner_sme: carlos.reyes@example-org.com
co_owner_departments:
  - soc-operations
co_owner_smes:
  - priya.nair@example-org.com
audience:
  - customer-service
  - product
document_type: runbook
content_category: incident-management
version: 1
lifecycle_state: active
approval_status: partial
approvals_required: 2
approved_by:
  - carlos.reyes@example-org.com
approved_at:
  - "2026-03-22T16:45:00Z"
approved_departments:
  - incident-management
pending_approval_from: priya.nair@example-org.com
pending_approval_department: soc-operations
pending_since: "2026-03-22T16:45:00Z"
escalation_sent: true
escalation_sent_at: "2026-03-22T16:46:00Z"
escalation_jira_subtask: PROD-1299-SUB-2
confidence_score: 0.88
agent_id: incident-agent-v1.0
tags:
  - sentinelone
  - v8-upgrade
  - PROD-1234
  - incident-management
  - soc-operations
  - runbook
  - active
  - partial
---

> **Approval Status — Partial**
> Approved by: carlos.reyes@example-org.com, incident-management — 2026-03-22T16:45:00Z
> Pending: priya.nair@example-org.com, soc-operations (escalation sent 2026-03-22)
> This document is active and authoritative. Full dual approval is outstanding.

---

# SentinelOne v8 Upgrade — Incident Management Runbook

> ⚠️ **Note**: This runbook has been approved by Incident Management.
> SOC Operations approval is pending. Review for SOC-specific alert threshold
> changes before relying on Section 4 for live incidents.

## 1. Scope

This runbook covers incident response procedures for issues arising from or
during the SentinelOne v8 platform upgrade. It supersedes the v7 runbook
(archived at `incident-management/PROD-1180/archived/`).

## 2. Pre-Upgrade Verification

Before the upgrade window opens, confirm:

- [ ] All endpoint agent policies have been reviewed for auto-update settings
- [ ] MFA has been pre-enrolled for all console users with admin access
- [ ] A maintenance window has been communicated to affected teams
- [ ] The rollback plan has been reviewed (see Section 6)

## 3. During Upgrade — Monitoring

Monitor the following in the SentinelOne console during the upgrade window:

| Signal | Normal | Escalate If |
|---|---|---|
| Agent check-in rate | >95% within 30 min | <80% after 45 min |
| Console login errors | <5 per hour | >20 per hour |
| Policy sync failures | 0 | Any failure during upgrade window |

## 4. Alert Threshold Changes in v8

> ⚠️ CONTEXT GAP — SOC Operations sign-off pending on thresholds below.
> These values are carried forward from v7 configuration. Priya Nair (SOC) to confirm.

| Alert Type | v7 Threshold | v8 Threshold (proposed) | Status |
|---|---|---|---|
| Agent offline | 15 min | 10 min | Pending SOC confirmation |
| Policy drift | 30 min | 15 min | Pending SOC confirmation |
| Console auth failures | 10/hour | 10/hour | Unchanged |

## 5. Incident Classification

| Severity | Criteria | Response SLA |
|---|---|---|
| P1 | >20% endpoints offline OR complete console outage | 15 min |
| P2 | 5–20% endpoints offline OR MFA system failure | 1 hour |
| P3 | <5% endpoints offline OR non-critical feature unavailable | 4 hours |

## 6. Rollback Procedure

SentinelOne v8 does not support in-platform rollback to v7.

If a P1 incident cannot be resolved within 2 hours:
1. Engage SentinelOne support (Priority support line: in customer portal)
2. Isolate affected endpoints from the policy group if necessary
3. Escalate to CISO if >40% endpoint coverage is lost

## 7. Post-Incident Actions

- Update this runbook within 24 hours of any P1 or P2 incident
- File a variance detection note if practitioner actions differed from this runbook
- Link the incident ticket to this Jira ID (PROD-1234) for traceability

## Related Content

- CS Support Guide: `PROD-1234_sentinelone_v8-upgrade_customer-service_support-guide_v1.md`
- Deprecated v7 runbook: archived in `incident-management/PROD-1180/archived/`

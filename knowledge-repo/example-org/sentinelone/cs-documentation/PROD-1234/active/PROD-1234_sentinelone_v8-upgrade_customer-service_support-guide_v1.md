---
jira_id: PROD-1234
jira_url: https://example-org.atlassian.net/browse/PROD-1234
product: sentinelone
feature: v8-upgrade
owner_department: customer-service
owner_sme: jane.smith@example-org.com
co_owner_departments: []
co_owner_smes: []
audience:
  - sales
  - product-marketing
document_type: support-guide
content_category: cs-documentation
version: 1
lifecycle_state: active
approval_status: full
approvals_required: 1
approved_by:
  - jane.smith@example-org.com
approved_at:
  - "2026-03-22T14:32:00Z"
approved_departments:
  - customer-service
pending_approval_from: null
pending_approval_department: null
pending_since: null
escalation_sent: false
escalation_sent_at: null
escalation_jira_subtask: null
confidence_score: 0.91
agent_id: cs-doc-agent-v1.0
tags:
  - sentinelone
  - v8-upgrade
  - PROD-1234
  - customer-service
  - support-guide
  - active
  - full
---

> **Approval Status — Full**
> Approved by: jane.smith@example-org.com, customer-service — 2026-03-22T14:32:00Z
> This document is active and authoritative.

---

# SentinelOne v8 Upgrade — CS Support Guide

## What Changed

SentinelOne has released version 8 of their EDR platform. The primary changes
affecting customer interactions are:

- The Deep Visibility module has been replaced with a unified visibility layer
  accessible from the main console sidebar
- Agent auto-update behaviour has changed: endpoints now update silently by default
  unless a policy override is configured
- The Management Console login flow now requires MFA for all users

## Customer Impact

Customers may contact support for the following reasons:

- They cannot locate the Deep Visibility module (it has moved / been renamed)
- Endpoint agents have updated automatically and they were not expecting this
- MFA prompts are appearing on console login for the first time
- Reports generated in v7 format may not open correctly in v8

## Step-by-Step Guide

### Locating the Unified Visibility Layer (replaces Deep Visibility)

1. Log in to the SentinelOne Management Console
2. From the left sidebar, select **Visibility** (previously labelled "Deep Visibility")
3. The interface has been redesigned — all prior functionality is available under
   the **Investigate** and **Hunt** tabs within the Visibility section
4. Saved queries from v7 can be imported: go to **Visibility > Hunt > Import Query**

### Disabling Silent Auto-Update (if customer requires manual control)

1. Navigate to **Settings > Updates > Endpoint Update Policy**
2. Change the update mode from "Automatic" to "Scheduled" or "Manual"
3. Save the policy — this will apply to all endpoints in the selected group

### Enabling / Troubleshooting MFA

1. MFA is now mandatory for all console users — this cannot be disabled
2. Supported methods: Authenticator app (TOTP) or email OTP
3. If a user is locked out: Admin can reset MFA at **Settings > Users > [username] > Reset MFA**

## Troubleshooting

| Issue | Likely Cause | Resolution |
|---|---|---|
| Cannot find Deep Visibility | Module renamed in v8 | Direct to Visibility > Investigate |
| Endpoints updated unexpectedly | Auto-update policy default changed | Update the endpoint policy to Manual |
| MFA loop on login | Browser caching old session | Clear browser cache; use incognito |
| v7 reports not opening | Format change between versions | Re-run report in v8 console |
| Console slow after upgrade | Cache rebuild post-upgrade | Allow 15–30 min; escalate if persists |

## FAQs

**Q: Will our custom v7 integrations still work in v8?**
A: Most API integrations are backward compatible. Customers using the Deep Visibility
API endpoint should review the v8 API migration guide available in the SentinelOne
customer portal.

**Q: Do we need to re-deploy agents to all endpoints?**
A: No. If auto-update is enabled, agents update silently. If manual mode is set,
agents will need to be pushed via the console update workflow.

**Q: Can customers roll back to v7 if they experience issues?**
A: Rollback is not supported from v8 to v7. Escalate to SentinelOne support if a
customer requires emergency rollback assistance.

**Q: Is there a training resource for the new console?**
A: SentinelOne has published a v8 admin training module in their customer portal
under Resources > Training > v8 Platform Overview.

## Related Content

- Incident Management runbook for v8 upgrade: `PROD-1234_sentinelone_v8-upgrade_incident-management_runbook_v1.md`
- Deprecated v7 guidance: archived in `cs-documentation/PROD-1180/archived/`

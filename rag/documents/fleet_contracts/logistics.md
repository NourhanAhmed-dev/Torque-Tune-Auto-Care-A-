---
doc_type: contract
client_id: 1
company_name: Delta Logistics Co.
tier: standard
---

# B2B Fleet Rescue Contract — Delta Logistics Co. (client_id: 1)

## Coverage
- Roadside rescue and towing for all registered fleet vehicles (BMW 320i, Audi A4)
  within Alexandria and Cairo metro areas.
- Covers mechanical breakdown, flat tire, battery failure, and engine failure.
- Does NOT cover collision/accident recovery — those are routed to the insurance
  claims graph, not fleet rescue.

## Auto-approval threshold
- Rescues costing **up to $500** may be auto-approved by the agent with no
  human sign-off.
- Any rescue **above $500** requires HITL approval from a fleet manager before
  a tow truck is dispatched.

## Dispatch constraints
- Max distance from breakdown to provider: **50 km**.
- Only providers on the "approved_providers_only" list may be dispatched.
- Standard tier: no requirement for photo evidence before dispatch.

## Provider network
- Preferred providers: PROV-001, PROV-004.
- Backup providers: PROV-002.

## Escalation
- If no approved provider responds within 45 minutes, escalate to fleet manager
  regardless of cost.
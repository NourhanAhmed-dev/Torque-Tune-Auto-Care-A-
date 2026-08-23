---
doc_type: contract
client_id: 2
company_name: Nile Freight FleetCo
tier: premium
---

# B2B Fleet Rescue Contract — Nile Freight FleetCo (client_id: 2)

## Coverage
- Roadside rescue and towing for all registered fleet vehicles (Mercedes C200
  and future additions) nationwide, not limited to Cairo/Alexandria.
- Covers mechanical breakdown, flat tire, battery failure, engine failure,
  and lockout assistance.

## Auto-approval threshold
- Premium tier: rescues costing **up to $1,200** may be auto-approved with
  no human sign-off — this client pre-negotiated a higher ceiling in exchange
  for a flat monthly retainer.
- Any rescue **above $1,200** requires HITL approval from the FleetCo account
  manager.

## Dispatch constraints
- Max distance from breakdown to provider: **80 km** (nationwide coverage
  requires a wider radius than the standard tier).
- Only providers on the "approved_providers_only" list may be dispatched.
- Premium tier REQUIRES photo evidence of the vehicle/breakdown before a tow
  truck is dispatched — if no photo is available in state, the dispatch node
  must treat this as a policy violation, not a fatal error, and route to HITL
  with reason "missing required photo evidence".

## Provider network
- Preferred providers: PROV-003, PROV-005.
- Backup providers: PROV-001.

## Escalation
- If no approved provider responds within 20 minutes (premium SLA is tighter
  than standard), escalate to the account manager regardless of cost.
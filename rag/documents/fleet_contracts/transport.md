---
doc_type: contract
client_id: 3
company_name: Giza Transport Group
tier: budget
---

# B2B Fleet Rescue Contract — Giza Transport Group (client_id: 3)

## Coverage
- Roadside rescue and towing for registered fleet vehicles within Giza only.
- Covers flat tire and battery failure ONLY — engine failure and other major
  mechanical issues are explicitly OUT OF SCOPE for this budget-tier contract
  and must be flagged for manual routing, not auto-dispatched.

## Auto-approval threshold
- Budget tier: rescues costing **up to $300** may be auto-approved with no
  human sign-off — this is the strictest ceiling of the three contracts on
  file.
- Any rescue **above $300** requires HITL approval from the client directly
  (no account manager on this tier — the admin task goes straight to the
  client's registered contact).

## Dispatch constraints
- Max distance from breakdown to provider: **30 km**.
- Substitute providers are NOT allowed under this contract — if the preferred
  provider is unavailable, this must open a HITL request, not silently
  substitute a different provider.

## Provider network
- Preferred provider: PROV-002 (sole approved provider — no backups on file).

## Escalation
- If PROV-002 does not respond within 60 minutes, open a HITL request; do not
  auto-substitute another provider under any circumstance.
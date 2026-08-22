# State Graph Architecture

## Graph 1: Post-Tune Comeback / Warranty Dispute Investigation

Graph 1 handles cases where a customer returns after a tuning or remap service and reports a problem with the vehicle.

The investigation may require a physical inspection, human review, and waiting for external events. Therefore, the workflow uses a persistent state graph with checkpointing.

## State Flow

```text
START
  ↓
INTAKE_COMPLAINT
  ↓
LINK_TO_ORIGINAL_LOG
  ↓
SCHEDULE_INSPECTION
  ↓
WAITING_INSPECTION
  ↓
INSPECTION
  ├── inconclusive → TICKET_OPEN
  │
  └── confirmed_issue / other result
          ↓
DETERMINE_RESPONSIBILITY
          ↓
WAITING_HITL
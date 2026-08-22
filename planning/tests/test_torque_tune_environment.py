from __future__ import annotations

from planning.torque_tune_environment import PlanningContext, TorqueTuneEnvironment


def _context(**overrides) -> PlanningContext:
    values = {
        "client_id": 2,
        "vehicle_id": 3,
        "tech_id": 2,
        "appointment_id": 3,
        "technician_authenticated": True,
        "disclosure_confirmed": False,
        "request_text": "Release an ECU remap and decat job.",
    }
    values.update(overrides)
    return PlanningContext(**values)


def test_release_without_disclosure_is_rejected():
    feedback = TorqueTuneEnvironment(_context()).evaluate(
        "Decision: RELEASE\n1. Log modification.\n2. Create invoice."
    )
    assert feedback.success is False
    assert any("disclosure" in detail.lower() for detail in feedback.details)


def test_hold_for_missing_disclosure_is_accepted():
    feedback = TorqueTuneEnvironment(_context()).evaluate(
        "Decision: HOLD\n1. Request customer disclosure.\n2. Escalate to the shift lead."
    )
    assert feedback.success is True
    assert any("appointment 3 matches" in detail.lower() for detail in feedback.details)


def test_unknown_vehicle_is_rejected_even_when_plan_holds():
    feedback = TorqueTuneEnvironment(_context(vehicle_id=999)).evaluate(
        "Decision: HOLD\n1. Ask the shift lead to correct the vehicle reference."
    )
    assert feedback.success is False
    assert any("unknown" in detail.lower() for detail in feedback.details)

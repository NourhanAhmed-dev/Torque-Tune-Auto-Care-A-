"""Grounded environment feedback for Torque-Tune planning candidates.

This module is deliberately outside ``planning_toolkit``.  The fork owns the
generic planning algorithms; this project owns the adapter to its real SQLite
database and MCP-session evidence.
"""

from __future__ import annotations

from pydoc import text
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from planning_toolkit.planning_lab.models import EnvironmentFeedback

_DECISIONS = re.compile(r"\b(RELEASE|HOLD|ESCALATE)\b", re.IGNORECASE)
_EMISSIONS_TERMS = re.compile(
    r"\b(ecu(?:\s+remap)?|decat|catalytic(?:\s+converter)?|dpf|egr)\b",
    re.IGNORECASE,
)
_INVOICE_TERMS = re.compile(r"\binvoice\b", re.IGNORECASE)
_LOG_TERMS = re.compile(
    r"\b(log(?:ging)?|record(?:ing)?|logged)\b[\s\S]{0,60}?\bmodification\b"
    r"|\bmodification\b[\s\S]{0,60}?\b(log(?:ging)?|record(?:ing)?|logged)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class PlanningContext:
    """Evidence available for one proposed job-release decision.

    ``technician_authenticated`` and ``disclosure_confirmed`` are intentionally
    explicit inputs: authentication and elicitation are session-level MCP
    outcomes, not facts that can be inferred from SQLite alone.
    """

    client_id: int
    vehicle_id: int
    tech_id: int
    appointment_id: int | None = None
    technician_authenticated: bool = False
    disclosure_confirmed: bool | None = None
    modification_logged: bool = False
    request_text: str = ""


class TorqueTuneEnvironment:
    """Validate RELEASE/HOLD/ESCALATE plans against SQLite and MCP evidence."""

    def __init__(self, context: PlanningContext, db_path: Path | None = None) -> None:
        self.context = context
        self.db_path = (
            db_path or Path(__file__).resolve().parents[1] / "db" / "redline.db"
        )

    def evaluate(self, candidate_plan: str) -> EnvironmentFeedback:
        """Return deterministic external feedback; never ask an LLM to score itself."""
        text = candidate_plan or ""
        decision = self._decision(text)
        evidence, blocking = self._database_checks()
        emissions_affecting = bool(
            _EMISSIONS_TERMS.search(self.context.request_text + "\n" + text)
        )

        if decision is None:
            blocking.append("Plan must explicitly choose RELEASE, HOLD, or ESCALATE.")

        if decision == "RELEASE":
            if not self.context.technician_authenticated:
                blocking.append(
                    "Cannot RELEASE: the assigned technician is not authenticated in the MCP session."
                )
            if emissions_affecting and self.context.disclosure_confirmed is not True:
                blocking.append(
                    "Cannot RELEASE emissions-affecting work without successful MCP disclosure evidence."
                )
            invoice = _INVOICE_TERMS.search(text)
            log = _LOG_TERMS.search(text)
            if (
                invoice
                and not self.context.modification_logged
                and not (log and log.start() < invoice.start())
            ):
                blocking.append(
                    "Cannot invoice before successful modification logging; state that logging happens first."
                )

        if decision in {"HOLD", "ESCALATE"}:
            if _INVOICE_TERMS.search(text):
                blocking.append("HOLD/ESCALATE plans must not create an invoice.")
            if re.search(
                r"\b(mark|record|log)\b.{0,50}\bcomplete\b", text, re.IGNORECASE
            ):
                blocking.append(
                    "HOLD/ESCALATE plans must not mark the modification complete."
                )

        if decision == "RELEASE" and not re.search(
            r"\b(next action|next step|1[.)])", text, re.IGNORECASE
        ):
            blocking.append(
                "A RELEASE plan must include concrete next actions in execution order."
            )

        details = evidence + blocking
        score = max(0.0, 1.0 - (0.2 * len(blocking)))
        return EnvironmentFeedback(success=not blocking, score=score, details=details)

    def _database_checks(self) -> tuple[list[str], list[str]]:
        evidence: list[str] = []
        blocking: list[str] = []
        if not self.db_path.exists():
            return evidence, [f"Database not found: {self.db_path}"]

        with sqlite3.connect(self.db_path) as connection:
            connection.row_factory = sqlite3.Row
            vehicle = connection.execute(
                "SELECT vehicle_id FROM vehicles WHERE vehicle_id = ? AND client_id = ?",
                (self.context.vehicle_id, self.context.client_id),
            ).fetchone()
            if vehicle:
                evidence.append(
                    f"SQLite: vehicle {self.context.vehicle_id} belongs to client {self.context.client_id}."
                )
            else:
                blocking.append(
                    f"SQLite: vehicle {self.context.vehicle_id} is unknown or does not belong to client {self.context.client_id}."
                )

            technician = connection.execute(
                "SELECT tech_id FROM technicians WHERE tech_id = ?",
                (self.context.tech_id,),
            ).fetchone()
            if technician:
                evidence.append(f"SQLite: technician {self.context.tech_id} exists.")
            else:
                blocking.append(
                    f"SQLite: technician {self.context.tech_id} does not exist."
                )

            if self.context.appointment_id is not None:
                appointment = connection.execute(
                    "SELECT appointment_id FROM appointments "
                    "WHERE appointment_id = ? AND vehicle_id = ? AND tech_id = ?",
                    (
                        self.context.appointment_id,
                        self.context.vehicle_id,
                        self.context.tech_id,
                    ),
                ).fetchone()
                if appointment:
                    evidence.append(
                        f"SQLite: appointment {self.context.appointment_id} matches the vehicle and technician."
                    )
                else:
                    blocking.append(
                        f"SQLite: appointment {self.context.appointment_id} does not match the vehicle and technician."
                    )

        return evidence, blocking

    @staticmethod
    def _decision(candidate_plan: str) -> str | None:
        text = candidate_plan or ""

        patterns = [
            # FINAL_DECISION: HOLD
            r"\bFINAL_DECISION\s*:\s*(RELEASE|HOLD|ESCALATE)\b",

            # Decision: HOLD / **Decision:** HOLD
            r"\*{0,2}\s*decision\s*\*{0,2}\s*:\s*(RELEASE|HOLD|ESCALATE)\b",

            # Status: HOLD / **Status:** HOLD
            r"\*{0,2}\s*status\s*\*{0,2}\s*:\s*(RELEASE|HOLD|ESCALATE)\b",
    ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).upper()

        # Final Decision section
        final_section = re.search(
            r"(?:final\s+decision|final\s+answer)\b([\s\S]{0,500})",
            text,
            re.IGNORECASE,
        )

        if final_section:
            match = re.search(
                r"\b(RELEASE|HOLD|ESCALATE)\b",
                final_section.group(1),
                re.IGNORECASE,
            )
            if match:
                return match.group(1).upper()

        return None
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from typing import Any, Iterable, Iterator

from state_graph.graphs.graph1_multi_supplier.state import InstallationStep


class SourcingRepository:
    """Thin data-access layer around the sourcing-related tables."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    # ------------------------------------------------------------------
    # connection helper — one transaction per call, commit/rollback safe
    # ------------------------------------------------------------------
    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ==================================================================
    # state_graph_runs  — run bookkeeping
    # ==================================================================
    def ensure_run(
        self,
        run_id: str,
        graph_type: str = "graph1_multi_supplier",
        status: str = "running",
        vehicle_id: int | None = None,
        client_id: int | None = None,
    ) -> None:
        """Create the run row if it doesn't already exist (idempotent)."""
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO state_graph_runs (run_id, graph_type, status, vehicle_id, client_id)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO NOTHING
                """,
                (run_id, graph_type, status, vehicle_id, client_id),
            )

    def update_run_state(
        self,
        run_id: str,
        *,
        status: str | None = None,
        current_state: dict[str, Any] | None = None,
    ) -> None:
        fields, params = [], []
        if status is not None:
            fields.append("status = ?")
            params.append(status)
        if current_state is not None:
            fields.append("current_state = ?")
            params.append(json.dumps(current_state, default=str))
        if not fields:
            return
        fields.append("updated_at = CURRENT_TIMESTAMP")
        params.append(run_id)
        with self._conn() as conn:
            conn.execute(
                f"UPDATE state_graph_runs SET {', '.join(fields)} WHERE run_id = ?",
                params,
            )

    # ==================================================================
    # supplier_orders / supplier_order_parts   -> SupplierOrderNode
    # ==================================================================
    def save_supplier_order(
        self,
        *,
        run_id: str,
        order_id: int,
        supplier: str,
        status: str,
        quoted_price: float,
        part_ids: Iterable[int],
        quantity_by_part: dict[int, int] | None = None,
        expected_delivery: str | None = None,
    ) -> None:
        """
        Persist a freshly placed order plus its line items in one transaction.
        Call this right after client.place_order() succeeds and the response
        has been validated.
        """
        quantity_by_part = quantity_by_part or {}
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO supplier_orders
                    (order_id, run_id, supplier, status, quoted_price, expected_delivery)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(order_id) DO UPDATE SET
                    status             = excluded.status,
                    quoted_price       = excluded.quoted_price,
                    expected_delivery  = excluded.expected_delivery,
                    updated_at         = CURRENT_TIMESTAMP
                """,
                (order_id, run_id, supplier, status, quoted_price, expected_delivery),
            )
            for part_id in part_ids:
                conn.execute(
                    """
                    INSERT INTO supplier_order_parts (order_id, part_id, quantity, status)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(order_id, part_id) DO UPDATE SET
                        quantity = excluded.quantity,
                        status   = excluded.status
                    """,
                    (order_id, part_id, quantity_by_part.get(part_id, 1), "ordered"),
                )

    def record_order_failure(self, order_id: int, error_message: str) -> None:
        """Bump api_attempts / last_api_error after a retryable failure."""
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE supplier_orders
                SET api_attempts   = api_attempts + 1,
                    last_api_error = ?,
                    updated_at     = CURRENT_TIMESTAMP
                WHERE order_id = ?
                """,
                (error_message, order_id),
            )

    def update_order_status(
        self, order_id: int, status: str, actual_delivery: str | None = None
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE supplier_orders
                SET status          = ?,
                    actual_delivery = COALESCE(?, actual_delivery),
                    updated_at      = CURRENT_TIMESTAMP
                WHERE order_id = ?
                """,
                (status, actual_delivery, order_id),
            )

    def get_order(self, order_id: int) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM supplier_orders WHERE order_id = ?", (order_id,)
            ).fetchone()
            return dict(row) if row else None

    # ==================================================================
    # supplier_orders.final_price   -> PriceCheckNode
    # ==================================================================
    def update_final_price(self, order_id: int, final_price: float) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE supplier_orders
                SET final_price = ?, updated_at = CURRENT_TIMESTAMP
                WHERE order_id = ?
                """,
                (final_price, order_id),
            )

    # ==================================================================
    # supplier_order_parts.substitute_part / warranty_impact
    #   -> SubstituteCheckNode
    # ==================================================================
    def apply_substitute(
        self,
        *,
        order_id: int,
        part_id: int,
        substitute_part: str | None,
        warranty_impact: str | None,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE supplier_order_parts
                SET substitute_part = ?, warranty_impact = ?
                WHERE order_id = ? AND part_id = ?
                """,
                (substitute_part, warranty_impact, order_id, part_id),
            )

    # ==================================================================
    # installation_steps   -> TaskDecompositionNode
    # ==================================================================
    def save_installation_steps(self, run_id: str, steps: list[InstallationStep]) -> None:
        """
        Replace the run's installation plan with the freshly scheduled steps.
        Called once, after dynamic_decomposition finishes.
        """
        with self._conn() as conn:
            conn.execute("DELETE FROM installation_steps WHERE run_id = ?", (run_id,))
            for step in steps:
                conn.execute(
                    """
                    INSERT INTO installation_steps
                        (run_id, part_id, step_order, description, status, dependencies)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        step["part_id"],
                        step["step_order"],
                        step["description"],
                        step.get("status", "pending"),
                        json.dumps(step.get("dependencies", [])),
                    ),
                )

    def update_step_status(self, run_id: str, part_id: int, status: str) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE installation_steps
                SET status = ?
                WHERE run_id = ? AND part_id = ?
                """,
                (status, run_id, part_id),
            )

    # ==================================================================
    # supplier_events  — audit trail for anything that happened
    #   (order placed, price deviation, substitute offered, webhooks...)
    # ==================================================================
    def log_event(
        self,
        *,
        run_id: str,
        order_id: int | None,
        event_type: str,
        payload: dict[str, Any],
        status: str = "received",
    ) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO supplier_events (run_id, order_id, event_type, payload, status)
                VALUES (?, ?, ?, ?, ?)
                """,
                (run_id, order_id, event_type, json.dumps(payload, default=str), status),
            )
            return cur.lastrowid

    def mark_event_processed(self, event_id: int) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE supplier_events
                SET status = 'processed', processed_at = CURRENT_TIMESTAMP
                WHERE event_id = ?
                """,
                (event_id,),
            )
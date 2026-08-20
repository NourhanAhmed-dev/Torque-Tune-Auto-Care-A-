import unittest

from state_graph.graph1 import Graph1
from state_graph.schema import RunStatus


class TestGraph1(unittest.TestCase):

    def setUp(self):
        self.graph = Graph1()
        self.run_id = "test_graph1"

        if self.graph.checkpoints.exists(self.run_id):
            self.graph.checkpoints.delete(self.run_id)

    def tearDown(self):
        if self.graph.checkpoints.exists(self.run_id):
            self.graph.checkpoints.delete(self.run_id)

    def move_to_waiting_inspection(self, state):
        """Move a run from START to WAITING_INSPECTION."""
        for _ in range(4):
            state = self.graph.step(state)
        return state

    def test_start_creates_initial_state(self):
        state = self.graph.start(self.run_id)

        self.assertEqual(state.current_node, "START")
        self.assertEqual(state.status, RunStatus.RUNNING)
        self.assertEqual(state.run_id, self.run_id)
        self.assertEqual(state.graph_name, "graph1")

    def test_graph_transitions_to_waiting_inspection(self):
        state = self.graph.start(self.run_id)

        state = self.graph.step(state)
        self.assertEqual(
            state.current_node,
            "INTAKE_COMPLAINT",
        )

        state = self.graph.step(state)
        self.assertEqual(
            state.current_node,
            "LINK_TO_ORIGINAL_LOG",
        )

        state = self.graph.step(state)
        self.assertEqual(
            state.current_node,
            "SCHEDULE_INSPECTION",
        )

        state = self.graph.step(state)
        self.assertEqual(
            state.current_node,
            "WAITING_INSPECTION",
        )

        self.assertEqual(
            state.status,
            RunStatus.WAITING_EXTERNAL,
        )

    def test_inspection_result_continues_investigation(self):
        state = self.graph.start(self.run_id)

        state = self.move_to_waiting_inspection(state)

        state = self.graph.submit_inspection_result(
            state,
            "confirmed_issue",
        )

        self.assertEqual(
            state.current_node,
            "INSPECTION",
        )
        self.assertEqual(
            state.status,
            RunStatus.RUNNING,
        )
        self.assertEqual(
            state.payload["inspection_result"],
            "confirmed_issue",
        )

    def test_inconclusive_inspection_opens_ticket(self):
        state = self.graph.start(self.run_id)

        state = self.move_to_waiting_inspection(state)

        state = self.graph.submit_inspection_result(
            state,
            "inconclusive",
        )

        self.assertEqual(
            state.current_node,
            "TICKET_OPEN",
        )
        self.assertEqual(
            state.status,
            RunStatus.TICKET_OPEN,
        )
        self.assertEqual(
            state.payload["inspection_result"],
            "inconclusive",
        )

    def test_normal_path_reaches_hitl(self):
        state = self.graph.start(self.run_id)

        state = self.move_to_waiting_inspection(state)

        state = self.graph.submit_inspection_result(
            state,
            "confirmed_issue",
        )

        state = self.graph.step(state)
        self.assertEqual(
            state.current_node,
            "DETERMINE_RESPONSIBILITY",
        )

        state = self.graph.step(state)
        self.assertEqual(
            state.current_node,
            "WAITING_HITL",
        )

        self.assertEqual(
            state.status,
            RunStatus.WAITING_HITL,
        )

    def test_checkpoint_is_saved(self):
        state = self.graph.start(self.run_id)

        state = self.move_to_waiting_inspection(state)

        loaded = self.graph.get_state(self.run_id)

        self.assertEqual(
            loaded.current_node,
            "WAITING_INSPECTION",
        )
        self.assertEqual(
            loaded.status,
            RunStatus.WAITING_EXTERNAL,
        )
        self.assertEqual(
            loaded.run_id,
            self.run_id,
        )

    def test_crash_restart_recovers_waiting_state(self):
        state = self.graph.start(self.run_id)

        state = self.move_to_waiting_inspection(state)

        self.assertEqual(
            state.current_node,
            "WAITING_INSPECTION",
        )

        # Simulate application crash by creating a new Graph1.
        new_graph = Graph1()

        recovered = new_graph.get_state(self.run_id)

        self.assertEqual(
            recovered.current_node,
            "WAITING_INSPECTION",
        )
        self.assertEqual(
            recovered.status,
            RunStatus.WAITING_EXTERNAL,
        )

    def test_resume_does_not_skip_waiting_inspection(self):
        state = self.graph.start(self.run_id)

        state = self.move_to_waiting_inspection(state)

        new_graph = Graph1()

        resumed = new_graph.resume(self.run_id)

        self.assertEqual(
            resumed.current_node,
            "WAITING_INSPECTION",
        )
        self.assertEqual(
            resumed.status,
            RunStatus.WAITING_EXTERNAL,
        )

    def test_payload_is_persisted(self):
        payload = {
            "vehicle_id": "TEST-123",
            "complaint": "engine_light",
        }

        state = self.graph.start(
            self.run_id,
            payload=payload,
        )

        loaded = self.graph.get_state(self.run_id)

        self.assertEqual(
            loaded.payload,
            payload,
        )

    def test_history_records_graph_states(self):
        state = self.graph.start(self.run_id)

        state = self.move_to_waiting_inspection(state)

        history = self.graph.checkpoints.history(
            self.run_id
        )

        self.assertGreaterEqual(
            len(history),
            5,
        )

        nodes = [
            record["current_node"]
            for record in history
        ]

        self.assertIn("START", nodes)
        self.assertIn("INTAKE_COMPLAINT", nodes)
        self.assertIn("LINK_TO_ORIGINAL_LOG", nodes)
        self.assertIn("SCHEDULE_INSPECTION", nodes)
        self.assertIn("WAITING_INSPECTION", nodes)

    def test_invalid_transition(self):
        state = self.graph.start(self.run_id)

        state.current_node = "INVALID_NODE"

        with self.assertRaises(ValueError):
            self.graph.step(state)


if __name__ == "__main__":
    unittest.main()
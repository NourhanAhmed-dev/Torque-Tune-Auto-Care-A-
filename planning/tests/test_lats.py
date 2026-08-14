import unittest
from unittest.mock import Mock, patch

from planning.lats import run_lats
from planning.models import PlanningDecision, PlanningRequest, PlanningResult
from planning.plan_and_solve import build_planning_question, plan_job
from planning.tree_of_thoughts import (
    build_tot_question,
    evaluate_decisions,
)
from planning.router import PlanningMethod, route_subtask, select_algorithm


class TestLATS(unittest.TestCase):

    @patch("planning.lats.toolkit_lats")
    def test_run_lats_passes_arguments_correctly(self, mock_lats):
        mock_llm = Mock()
        mock_environment = Mock()
        expected_result = Mock()

        mock_lats.return_value = expected_result

        result = run_lats(
            task="Review ECU remap",
            llm=mock_llm,
            environment=mock_environment,
            iterations=3,
            n_actions=4,
            exploration_weight=2.0,
        )

        mock_lats.assert_called_once_with(
            task="Review ECU remap",
            llm=mock_llm,
            environment=mock_environment,
            iterations=3,
            n_actions=4,
            exploration_weight=2.0,
        )

        self.assertIs(result, expected_result)


class TestPlanAndSolve(unittest.TestCase):

    def test_build_planning_question_contains_request_data(self):
        request = PlanningRequest(
            request="Review ECU remap",
            client_id=1,
            vehicle_id=2,
            tech_id=3,
            appointment_id=4,
        )

        question = build_planning_question(request)

        self.assertIn("Review ECU remap", question)
        self.assertIn("Client ID: 1", question)
        self.assertIn("Vehicle ID: 2", question)
        self.assertIn("Technician ID: 3", question)
        self.assertIn("Appointment ID: 4", question)

    @patch("planning.plan_and_solve.toolkit_plan_and_solve")
    def test_plan_job_calls_toolkit(self, mock_toolkit):
        mock_toolkit.return_value = "plan result"
        llm = Mock()

        request = PlanningRequest(
            request="Review ECU remap",
            client_id=1,
            vehicle_id=2,
            tech_id=3,
            appointment_id=4,
        )

        result = plan_job(request, llm)

        mock_toolkit.assert_called_once()
        self.assertEqual(result, "plan result")


class TestTreeOfThoughts(unittest.TestCase):

    def test_build_tot_question_contains_request_data(self):
        request = PlanningRequest(
            request="Compare release or hold",
            client_id=1,
            vehicle_id=2,
            tech_id=3,
            appointment_id=4,
        )

        question = build_tot_question(request)

        self.assertIn("Compare release or hold", question)
        self.assertIn("Client ID: 1", question)
        self.assertIn("Vehicle ID: 2", question)
        self.assertIn("Technician ID: 3", question)
        self.assertIn("Appointment ID: 4", question)

    @patch("planning.tree_of_thoughts.toolkit_tree_of_thoughts")
    def test_evaluate_decisions_calls_toolkit(self, mock_toolkit):
        mock_toolkit.return_value = []
        llm = Mock()

        request = PlanningRequest(
            request="Compare release or hold",
            client_id=1,
            vehicle_id=2,
            tech_id=3,
            appointment_id=4,
        )

        result = evaluate_decisions(
            request,
            llm,
            depth=3,
            beam_width=4,
        )

        mock_toolkit.assert_called_once()
        self.assertEqual(result, [])


class TestRouter(unittest.TestCase):

    def test_route_comparison_to_tree_of_thoughts(self):
        result = route_subtask("Compare release or hold")
        self.assertEqual(result, PlanningMethod.TREE_OF_THOUGHTS)

    def test_route_external_validation_to_lats(self):
        result = route_subtask("Perform final decision using MCP evidence")
        self.assertEqual(result, PlanningMethod.LATS)

    def test_route_normal_planning_to_plan_and_solve(self):
        result = route_subtask("Verify client and vehicle identity")
        self.assertEqual(result, PlanningMethod.PLAN_AND_SOLVE)

    def test_select_algorithm(self):
        algorithms = {
            PlanningMethod.PLAN_AND_SOLVE: "plan",
            PlanningMethod.TREE_OF_THOUGHTS: "tot",
        }

        result = select_algorithm(
            "Compare release or hold",
            algorithms,
        )

        self.assertEqual(result, "tot")


class TestPlanningResult(unittest.TestCase):

    def test_hold_result(self):
        result = PlanningResult(
            decision=PlanningDecision.HOLD,
            reasons=["Required evidence is missing"],
            evidence=["MCP verification required"],
            next_actions=["Do not perform database write"],
        )

        self.assertEqual(
            result.decision,
            PlanningDecision.HOLD,
        )
        self.assertIn(
            "Required evidence is missing",
            result.reasons,
        )
        self.assertIn(
            "MCP verification required",
            result.evidence,
        )
        self.assertIn(
            "Do not perform database write",
            result.next_actions,
        )

    def test_release_result(self):
        result = PlanningResult(
            decision=PlanningDecision.RELEASE,
            reasons=["All required evidence is verified"],
            evidence=[
                "Client, vehicle, appointment, and technician verified"
            ],
            next_actions=["Proceed with approved job"],
        )

        self.assertEqual(
            result.decision,
            PlanningDecision.RELEASE,
        )

    def test_escalate_result(self):
        result = PlanningResult(
            decision=PlanningDecision.ESCALATE,
            reasons=["Customer confirmation is required"],
            evidence=[
                "Modification requires additional confirmation"
            ],
            next_actions=["Escalate to shift lead"],
        )

        self.assertEqual(
            result.decision,
            PlanningDecision.ESCALATE,
        )


if __name__ == "__main__":
    unittest.main()
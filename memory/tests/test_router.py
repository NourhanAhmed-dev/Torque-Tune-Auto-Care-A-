import unittest

from memory.router import MemoryRouter


class TestMemoryRouter(unittest.TestCase):

    def setUp(self):
        self.router = MemoryRouter()

    def test_promote_important_message(self):

        message = {
            "role": "user",
            "content": "The client booked an appointment for vehicle maintenance.",
            "metadata": {
                "client_id": 1,
                "vehicle_id": 5
            }
        }

        result = self.router.route(message)

        self.assertIsNotNone(result)

    def test_discard_unimportant_message(self):

        message = {
            "role": "assistant",
            "content": "ok",
            "metadata": {}
        }

        result = self.router.route(message)

        self.assertIsNone(result)

    def test_classify_vehicle(self):

        category = self.router.classify(
            "Vehicle requires engine repair."
        )

        self.assertEqual(category, "vehicle")

    def test_classify_appointment(self):

        category = self.router.classify(
            "Appointment scheduled tomorrow."
        )

        self.assertEqual(category, "appointment")

    def test_classify_preference(self):

        category = self.router.classify(
            "Client prefers premium tuning."
        )

        self.assertEqual(category, "preference")

    def test_importance_score(self):

        message = {
            "role": "user",
            "content": "Remember this important appointment.",
            "metadata": {}
        }

        score = self.router.evaluate_importance(message)

        self.assertGreaterEqual(score, 5)

    def test_metadata_increases_score(self):

        base = {
            "role": "user",
            "content": "Appointment",
            "metadata": {}
        }

        with_metadata = {
            "role": "user",
            "content": "Appointment",
            "metadata": {
                "client_id": 1,
                "vehicle_id": 2
            }
        }

        self.assertGreater(
            self.router.evaluate_importance(with_metadata),
            self.router.evaluate_importance(base)
        )


if __name__ == "__main__":
    unittest.main()
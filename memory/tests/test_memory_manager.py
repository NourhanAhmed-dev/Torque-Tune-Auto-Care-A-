import unittest

from memory.memory_manager import MemoryManager


class TestMemoryManager(unittest.TestCase):

    def setUp(self):
        self.manager = MemoryManager()

        self.manager.short_term.clear()
        self.manager.episodic_store.clear()
        self.manager.semantic_store.clear()

    def test_add_message(self):

        self.manager.add_message(
            "user",
            "Hello"
        )

        self.assertEqual(
            len(self.manager.recent_messages()),
            1
        )

    def test_multiple_messages(self):

        self.manager.add_message(
            "user",
            "First"
        )

        self.manager.add_message(
            "assistant",
            "Second"
        )

        self.assertEqual(
            len(self.manager.recent_messages()),
            2
        )

    def test_recent_messages(self):

        self.manager.add_message(
            "user",
            "Testing"
        )

        recent = self.manager.recent_messages()

        self.assertEqual(
            recent[0]["content"],
            "Testing"
        )

    def test_consolidation(self):

        self.manager.episodic_store.add(
            self.manager.router.route({
                "role": "user",
                "content": "Client always prefers OEM parts.",
                "metadata": {}
            })
        )

        self.manager.consolidate()

        self.assertGreaterEqual(
            len(self.manager.semantic_memories()),
            1
        )

    def test_empty_semantic(self):

        self.assertEqual(
            len(self.manager.semantic_memories()),
            0
        )

    def test_empty_episodic(self):

        self.assertEqual(
            len(self.manager.episodic_memories()),
            0
        )


if __name__ == "__main__":
    unittest.main()
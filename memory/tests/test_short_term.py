import unittest

from memory.short_term import ShortTermMemory


class TestShortTermMemory(unittest.TestCase):

    def setUp(self):
        self.memory = ShortTermMemory(max_messages=3)

    def test_add_message(self):
        self.memory.add_message("user", "Hello")

        self.assertEqual(self.memory.size(), 1)

    def test_latest_message(self):
        self.memory.add_message("user", "First")
        self.memory.add_message("assistant", "Second")

        self.assertEqual(
            self.memory.latest()["content"],
            "Second"
        )

    def test_clear_memory(self):
        self.memory.add_message("user", "Hello")
        self.memory.clear()

        self.assertEqual(self.memory.size(), 0)

    def test_is_full(self):
        self.memory.add_message("user", "1")
        self.memory.add_message("user", "2")
        self.memory.add_message("user", "3")

        self.assertTrue(self.memory.is_full())

    def test_overflow(self):
        self.memory.add_message("user", "1")
        self.memory.add_message("user", "2")
        self.memory.add_message("user", "3")
        self.memory.add_message("user", "4")

        messages = self.memory.get_messages()

        self.assertEqual(len(messages), 3)
        self.assertEqual(messages[0]["content"], "2")


if __name__ == "__main__":
    unittest.main()
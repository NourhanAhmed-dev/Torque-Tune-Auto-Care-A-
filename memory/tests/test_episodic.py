import unittest

from memory.episodic_store import EpisodicStore
from memory.models import EpisodicMemory
from memory.utils import generate_id


class TestEpisodicStore(unittest.TestCase):

    def setUp(self):
        self.store = EpisodicStore()
        self.store.clear()

    def test_add_memory(self):

        memory = EpisodicMemory(
            memory_id=generate_id(),
            content="Client prefers synthetic oil.",
            memory_type="preference",
            importance=5,
        )

        self.store.add(memory)

        self.assertEqual(len(self.store.get_all()), 1)

    def test_clear_store(self):

        memory = EpisodicMemory(
            memory_id=generate_id(),
            content="Test memory",
            memory_type="general",
        )

        self.store.add(memory)
        self.store.clear()

        self.assertEqual(len(self.store.get_all()), 0)

    def test_find_client(self):

        memory = EpisodicMemory(
            memory_id=generate_id(),
            content="Client memory",
            memory_type="general",
            client_id=1,
        )

        self.store.add(memory)

        result = self.store.find_by_client(1)

        self.assertEqual(len(result), 1)

    def test_find_vehicle(self):

        memory = EpisodicMemory(
            memory_id=generate_id(),
            content="Vehicle memory",
            memory_type="vehicle",
            vehicle_id=2,
        )

        self.store.add(memory)

        result = self.store.find_by_vehicle(2)

        self.assertEqual(len(result), 1)

    def test_find_technician(self):

        memory = EpisodicMemory(
            memory_id=generate_id(),
            content="Tech memory",
            memory_type="repair",
            tech_id=5,
        )

        self.store.add(memory)

        result = self.store.find_by_technician(5)

        self.assertEqual(len(result), 1)


if __name__ == "__main__":
    unittest.main()
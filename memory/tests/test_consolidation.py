import unittest

from memory.consolidation import ConsolidationEngine
from memory.episodic_store import EpisodicStore
from memory.semantic_store import SemanticStore
from memory.models import EpisodicMemory
from memory.utils import generate_id


class TestConsolidation(unittest.TestCase):

    def setUp(self):
        self.engine = ConsolidationEngine()

        self.episodic = EpisodicStore()
        self.semantic = SemanticStore()

        self.episodic.clear()
        self.semantic.clear()

    def test_consolidation(self):

        episode = EpisodicMemory(
            memory_id=generate_id(),
            content="Client always prefers OEM parts.",
            memory_type="preference",
            importance=5,
        )

        self.episodic.add(episode)

        self.engine.consolidate()

        self.assertEqual(self.semantic.count(), 1)

    def test_low_importance_not_saved(self):

        episode = EpisodicMemory(
            memory_id=generate_id(),
            content="Hello",
            memory_type="general",
            importance=1,
        )

        self.episodic.add(episode)

        self.engine.consolidate()

        self.assertEqual(self.semantic.count(), 0)

    def test_category_preserved(self):

        episode = EpisodicMemory(
            memory_id=generate_id(),
            content="Vehicle engine repaired.",
            memory_type="repair",
            importance=5,
        )

        self.episodic.add(episode)

        self.engine.consolidate()

        semantic = self.semantic.get_all()[0]

        self.assertEqual(
            semantic["category"],
            "repair"
        )


if __name__ == "__main__":
    unittest.main()
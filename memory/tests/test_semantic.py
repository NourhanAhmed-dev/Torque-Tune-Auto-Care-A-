import unittest

from memory.semantic_store import SemanticStore
from memory.models import SemanticMemory
from memory.utils import generate_id


class TestSemanticStore(unittest.TestCase):

    def setUp(self):
        self.store = SemanticStore()
        self.store.clear()

    def test_add_fact(self):

        fact = SemanticMemory(
            fact_id=generate_id(),
            fact="BMW requires premium fuel.",
            category="vehicle",
        )

        self.store.add(fact)

        self.assertEqual(self.store.count(), 1)

    def test_search_keyword(self):

        fact = SemanticMemory(
            fact_id=generate_id(),
            fact="Engine tuning completed.",
            category="repair",
        )

        self.store.add(fact)

        result = self.store.search_keyword("engine")

        self.assertEqual(len(result), 1)

    def test_search_category(self):

        fact = SemanticMemory(
            fact_id=generate_id(),
            fact="Invoice paid.",
            category="invoice",
        )

        self.store.add(fact)

        result = self.store.search_category("invoice")

        self.assertEqual(len(result), 1)

    def test_search_client(self):

        fact = SemanticMemory(
            fact_id=generate_id(),
            fact="Client prefers OEM parts.",
            category="preference",
            client_id=10,
        )

        self.store.add(fact)

        result = self.store.search_client(10)

        self.assertEqual(len(result), 1)

    def test_active_records(self):

        fact = SemanticMemory(
            fact_id=generate_id(),
            fact="Vehicle serviced.",
            category="repair",
        )

        self.store.add(fact)

        self.assertEqual(len(self.store.search_active()), 1)


if __name__ == "__main__":
    unittest.main()
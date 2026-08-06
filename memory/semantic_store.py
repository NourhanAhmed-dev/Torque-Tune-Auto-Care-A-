from pathlib import Path
from dataclasses import asdict

from .utils import load_json, save_json
from .models import SemanticMemory
from .config import SEMANTIC_FILE


class SemanticStore:
    """
    Stores long-term semantic memories and supports searching.
    """

    def __init__(self):
        self.file_path = Path(__file__).parent / "storage" / SEMANTIC_FILE

        if not self.file_path.exists():
            save_json(self.file_path, [])

    def add(self, memory: SemanticMemory):
        memories = self.get_all()

        # Prevent duplicate active facts
        for m in memories:
            if (
                m["fact"].lower() == memory.fact.lower()
                and m["active"]
            ):
                return False

        memories.append(asdict(memory))
        save_json(self.file_path, memories)
        return True

    def get_all(self):
        return load_json(self.file_path)

    def clear(self):
        save_json(self.file_path, [])

    def update_fact(self, fact_id, new_fact):

        memories = self.get_all()

        for memory in memories:

            if memory["fact_id"] == fact_id:

                memory["fact"] = new_fact
                memory["version"] += 1

        save_json(self.file_path, memories)

    def deactivate(self, fact_id):

        memories = self.get_all()

        for memory in memories:

            if memory["fact_id"] == fact_id:

                memory["active"] = False

        save_json(self.file_path, memories)

    def search_keyword(self, keyword):

        keyword = keyword.lower()

        return [
            m
            for m in self.get_all()
            if keyword in m["fact"].lower()
        ]

    def search_category(self, category):

        return [
            m
            for m in self.get_all()
            if m["category"] == category
        ]

    def search_client(self, client_id):

        return [
            m
            for m in self.get_all()
            if m.get("client_id") == client_id
        ]

    def search_vehicle(self, vehicle_id):

        return [
            m
            for m in self.get_all()
            if m.get("vehicle_id") == vehicle_id
        ]

    def search_technician(self, tech_id):

        return [
            m
            for m in self.get_all()
            if m.get("tech_id") == tech_id
        ]

    def search_active(self):

        return [
            m
            for m in self.get_all()
            if m["active"]
        ]

    def count(self):
        return len(self.get_all())
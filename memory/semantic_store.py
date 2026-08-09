import datetime
from pathlib import Path
from dataclasses import asdict

from .utils import load_json, save_json
from .models import SemanticMemory
from .config import SEMANTIC_FILE

import re
from datetime import datetime, timezone

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

    def update(self, fact_id: str, updates: dict) -> None:
        """Update specific fields of a semantic fact (used by consolidation)."""
        from datetime import datetime
        facts = self.get_all()
        for f in facts:
            if f.get("fact_id") == fact_id:
                f.update(updates)
                if "updated_at" not in updates:
                    f["updated_at"] = datetime.utcnow()
                break
        save_json(self.file_path, facts)

    def deactivate(self, fact_id: str) -> None:
        self.update(fact_id, {"active": False, "updated_at": datetime.utcnow()})

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return {
            token.lower()
            for token in re.findall(r"[a-zA-Z0-9_-]{3,}", text or "")
        }

    @staticmethod
    def _is_expired(memory: dict) -> bool:
        raw = memory.get("expires_at")
        if not raw:
            return False

        try:
            expiry = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            return expiry <= datetime.now(timezone.utc)
        except ValueError:
            # Invalid expiry should never be treated as an active fact.
            return True

    def recall(
        self,
        query: str,
        *,
        client_id=None,
        vehicle_id=None,
        limit: int = 5,
    ) -> list[dict]:
        """
        Retrieve active, non-expired facts only.
        Scope is mandatory to avoid cross-client memory leakage.
        """
        if client_id is None and vehicle_id is None:
            return []

        query_tokens = self._tokens(query)
        candidates = []

        for fact in self.get_all():
            if not fact.get("active", True):
                continue
            if self._is_expired(fact):
                continue
            if client_id is not None and fact.get("client_id") != client_id:
                continue
            if vehicle_id is not None and fact.get("vehicle_id") != vehicle_id:
                continue

            overlap = len(query_tokens & self._tokens(fact.get("fact", "")))
            version = int(fact.get("version", 1))
            score = (overlap * 10) + version
            candidates.append((score, fact))

        candidates.sort(key=lambda item: item[0], reverse=True)
        return [fact for _, fact in candidates[:limit]]
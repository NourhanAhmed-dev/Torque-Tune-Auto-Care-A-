from pathlib import Path
from dataclasses import asdict

from .utils import load_json, save_json
from .models import EpisodicMemory
from .config import EPISODIC_FILE

import re
from datetime import datetime

class EpisodicStore:

    def __init__(self):
        self.file_path = Path(__file__).parent / "storage" / EPISODIC_FILE

        if not self.file_path.exists():
            save_json(self.file_path, [])

    def add(self, memory: EpisodicMemory):
        memories = load_json(self.file_path)
        memories.append(asdict(memory))
        save_json(self.file_path, memories)

    def get_all(self):
        return load_json(self.file_path)

    def clear(self):
        save_json(self.file_path, [])

    def find_by_client(self, client_id):
        return [
            m for m in self.get_all()
            if m.get("client_id") == client_id
        ]

    def find_by_vehicle(self, vehicle_id):
        return [
            m for m in self.get_all()
            if m.get("vehicle_id") == vehicle_id
        ]

    def find_by_technician(self, tech_id):
        return [
            m for m in self.get_all()
            if m.get("tech_id") == tech_id
        ]
    @staticmethod
    def _tokens(text: str) -> set[str]:
        return {
            token.lower()
            for token in re.findall(r"[a-zA-Z0-9_-]{3,}", text or "")
        }

    @staticmethod
    def _created_timestamp(memory: dict) -> float:
        raw = memory.get("created_at", "")
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
        except (TypeError, ValueError):
            return 0.0

    def recall(
        self,
        query: str,
        *,
        client_id=None,
        vehicle_id=None,
        limit: int = 5,
    ) -> list[dict]:
        """
        Return only relevant memories in the current client/vehicle scope.
        Returning nothing without a scope is safer than exposing all customers'
        history to the model.
        """
        if client_id is None and vehicle_id is None:
            return []

        query_tokens = self._tokens(query)
        candidates = []

        for memory in self.get_all():
            if client_id is not None and memory.get("client_id") != client_id:
                continue
            if vehicle_id is not None and memory.get("vehicle_id") != vehicle_id:
                continue

            overlap = len(query_tokens & self._tokens(memory.get("content", "")))
            importance = int(memory.get("importance", 0))
            recency = self._created_timestamp(memory) / 1_000_000_000

            score = (overlap * 10) + (importance * 2) + recency
            candidates.append((score, memory))

        candidates.sort(key=lambda item: item[0], reverse=True)
        return [memory for _, memory in candidates[:limit]]

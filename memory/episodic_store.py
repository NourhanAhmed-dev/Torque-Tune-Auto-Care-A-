from pathlib import Path
from dataclasses import asdict

from .utils import load_json, save_json
from .models import EpisodicMemory
from .config import EPISODIC_FILE


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
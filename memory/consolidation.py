from .episodic_store import EpisodicStore
from .semantic_store import SemanticStore
from .models import SemanticMemory
from .utils import generate_id, write_log
from .config import SEMANTIC_THRESHOLD


class ConsolidationEngine:
    """
    Converts important episodic memories into semantic memories.
    """

    def __init__(self):
        self.episodic_store = EpisodicStore()
        self.semantic_store = SemanticStore()

    def consolidate(self):

        episodes = self.episodic_store.get_all()

        for episode in episodes:

            if episode["importance"] < SEMANTIC_THRESHOLD:
                continue

            semantic = SemanticMemory(
                fact_id=generate_id(),
                fact=episode["content"],
                category=episode["memory_type"],
                source_episode=episode["memory_id"],
                client_id=episode.get("client_id"),
                vehicle_id=episode.get("vehicle_id"),
                tech_id=episode.get("tech_id"),
            )

            self.semantic_store.add(semantic)

            write_log(
                "consolidation",
                f"Consolidated {episode['memory_type']} | {episode['content']}",
            )
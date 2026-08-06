from .short_term import ShortTermMemory
from .scratchpad import Scratchpad
from .router import MemoryRouter
from .episodic_store import EpisodicStore
from .semantic_store import SemanticStore
from .consolidation import ConsolidationEngine


class MemoryManager:
    """
    Main controller for the memory system.
    """

    def __init__(self):
        self.short_term = ShortTermMemory()
        self.scratchpad = Scratchpad()
        self.router = MemoryRouter()

        self.episodic_store = EpisodicStore()
        self.semantic_store = SemanticStore()

        self.consolidation = ConsolidationEngine()

    def add_message(self, role, content, metadata=None):

        removed = self.short_term.add_message(
            role,
            content,
            metadata
        )

        if removed:

            memory = self.router.route(removed)

            if memory:
                self.episodic_store.add(memory)

    def consolidate(self):
        self.consolidation.consolidate()

    def recent_messages(self):
        return self.short_term.get_messages()

    def episodic_memories(self):
        return self.episodic_store.get_all()

    def semantic_memories(self):
        return self.semantic_store.get_all()
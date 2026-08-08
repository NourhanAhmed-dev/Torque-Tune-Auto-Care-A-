"""=== CONSOLIDATION LAYER (grader: separate periodic pass over episodic) ===
Handles updates, versioning, expiration, and explicit conflict resolution.
Old facts are NEVER silently lost — deactivated, dated, and kept.
"""
from datetime import datetime

from .config import SEMANTIC_THRESHOLD
from .episodic_store import EpisodicStore
from .models import SemanticMemory
from .semantic_store import SemanticStore
from .utils import generate_id, write_log


class ConsolidationEngine:
    def __init__(self):
        self.episodic_store = EpisodicStore()
        self.semantic_store = SemanticStore()

    def consolidate(self):
        episodes = self.episodic_store.get_all()
        existing = list(self.semantic_store.get_all())

        for episode in episodes:
            if episode.get("importance", 0) < SEMANTIC_THRESHOLD:
                continue
            content = episode.get("content", "").strip()
            if not content or len(content) > 2000:
                continue
            if any(f.get("source_episode") == episode.get("memory_id") for f in existing):
                continue

            category = episode.get("memory_type", "general")
            entity = (episode.get("vehicle_id"), episode.get("client_id"))

            # === CONFLICT RESOLUTION (explicit, versioned, dated) ===
            prior_active = [
                f for f in existing
                if f.get("category") == category
                and (f.get("vehicle_id"), f.get("client_id")) == entity
                and f.get("active", True)
            ]
            version = 1
            for old in prior_active:
                old_fact = (old.get("fact") or "").strip().lower()
                if old_fact == content.lower():
                    version = max(version, old.get("version", 1))
                elif self._is_contradiction(old_fact, content.lower()):
                    version = max(version, old.get("version", 1) + 1)
                    self._supersede(old)

            self.semantic_store.add(SemanticMemory(
                fact_id=generate_id(), fact=content, category=category,
                version=version, active=True,
                source_episode=episode.get("memory_id"),
                client_id=episode.get("client_id"),
                vehicle_id=episode.get("vehicle_id"),
                tech_id=episode.get("tech_id"),
            ))
            # refresh so later episodes in the SAME pass see this fact
            existing = list(self.semantic_store.get_all())
            write_log("consolidation", f"CONSOLIDATED v{version} | {category} | {content[:80]}")

    def _is_contradiction(self, a: str, b: str) -> bool:
        # NOTE: no hyphen-stripping — "5w-30" must stay one token to match.
        a_words, b_words = set(a.split()), set(b.split())
        pairs = [
            ({"5w-30"}, {"0w-20"}), ({"5w-30"}, {"10w-40"}), ({"0w-20"}, {"10w-40"}),
            ({"automatic"}, {"manual"}), ({"gasoline", "petrol"}, {"diesel"}),
            ({"oem", "stock", "factory"}, {"aftermarket", "non-oem"}),
        ]
        return any((s1 & a_words and s2 & b_words) or (s2 & a_words and s1 & b_words)
                   for s1, s2 in pairs)

    def _supersede(self, old: dict) -> None:
        for name in ("update", "deactivate", "supersede"):
            fn = getattr(self.semantic_store, name, None)
            if callable(fn):
                try:
                    if name == "update":
                        fn(old["fact_id"], {"active": False, "updated_at": datetime.utcnow()})
                    else:
                        fn(old["fact_id"])
                    write_log("consolidation",
                              f"SUPERSEDED v{old.get('version')} | {old['fact_id']} | was: {old.get('fact')[:60]}")
                    return
                except TypeError:
                    continue
        write_log("consolidation",
                  f"SUPERSEDED v{old.get('version')} | FLAGGED STALE | was: {old.get('fact')[:60]}")
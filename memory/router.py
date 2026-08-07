from .models import EpisodicMemory
from .utils import generate_id, write_log
from .config import IMPORTANCE_THRESHOLD


class MemoryRouter:
    """
    Decides whether a message should be promoted to episodic memory.
    Also assigns an importance score based on message content.
    """

    IMPORTANT_KEYWORDS = {
        "appointment": 2,
        "invoice": 2,
        "vehicle": 2,
        "client": 2,
        "technician": 2,
        "repair": 2,
        "service": 2,
        "tuning": 2,
        "engine": 2,
        "remember": 3,
        "always": 3,
        "never": 3,
        "important": 3,
        "preference": 2,
    }

    USELESS_MESSAGES = {
        "ok",
        "okay",
        "done",
        "thanks",
        "thank you",
        "hi",
        "hello",
        "yes",
        "no",
    }

    def __init__(self, importance_threshold=IMPORTANCE_THRESHOLD):
        self.importance_threshold = importance_threshold

    def classify(self, content):
        text = content.lower()

        if "appointment" in text:
            return "appointment"

        if "invoice" in text:
            return "invoice"

        if "vehicle" in text:
            return "vehicle"

        if "technician" in text:
            return "technician"

        if "repair" in text or "service" in text:
            return "repair"

        if "prefer" in text or "preference" in text:
            return "preference"

        return "general"

    def evaluate_importance(self, message):

        content = message["content"].lower()

        if content.strip() in self.USELESS_MESSAGES:
            return 0

        score = 1

        # Keyword scoring
        for keyword, points in self.IMPORTANT_KEYWORDS.items():
            if keyword in content:
                score += points

        # User messages are more important
        if message.get("role") == "user":
            score += 2

        # Longer messages usually contain more information
        if len(content) > 100:
            score += 1

        metadata = message.get("metadata", {})

        # Reward useful metadata
        for field in [
            "client_id",
            "vehicle_id",
            "tech_id",
            "appointment_id",
        ]:
            if field in metadata and metadata[field] is not None:
                score += 1

        return score

    def route(self, message):

        score = self.evaluate_importance(message)

        if score < self.importance_threshold:

            write_log(
                "router",
                f"DISCARDED | Score={score} | {message['content']}",
            )

            return None

        category = self.classify(message["content"])

        episodic = EpisodicMemory(
            memory_id=generate_id(),
            content=message["content"],
            memory_type=category,
            importance=score,
            client_id=message.get("metadata", {}).get("client_id"),
            vehicle_id=message.get("metadata", {}).get("vehicle_id"),
            tech_id=message.get("metadata", {}).get("tech_id"),
            appointment_id=message.get("metadata", {}).get("appointment_id"),
            metadata=message.get("metadata", {}),
        )

        write_log(
            "router",
            f"PROMOTED | {category.upper()} | Score={score} | {message['content']}",
        )

        return episodic
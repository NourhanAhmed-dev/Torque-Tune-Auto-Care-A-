from collections import deque

from .config import MAX_SHORT_TERM_MESSAGES


class ShortTermMemory:
    def __init__(self, max_messages=MAX_SHORT_TERM_MESSAGES):
        self.max_messages = max_messages
        self.messages = deque(maxlen=max_messages)

    def add_message(self, role, content, metadata=None):
        removed = None

        if len(self.messages) >= self.max_messages:
            removed = self.messages.popleft()

        self.messages.append({
            "role": role,
            "content": content,
            "metadata": metadata or {}
        })

        return removed

    def get_messages(self):
        return list(self.messages)

    def latest(self):
        if not self.messages:
            return None
        return self.messages[-1]

    def clear(self):
        self.messages.clear()

    def size(self):
        return len(self.messages)

    def is_full(self):
        return len(self.messages) >= self.max_messages
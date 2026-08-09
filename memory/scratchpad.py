class Scratchpad:
    """
    Temporary working memory for the current task.
    It is separate from chat history and must survive context pruning.
    """

    def __init__(self):
        self.reset()

    def set_goal(self, goal: str) -> None:
        self.goal = goal

    def add_step(self, step: str) -> None:
        if step and step not in self.plan:
            self.plan.append(step)

    def add_note(self, note: str) -> None:
        if note and note not in self.notes:
            self.notes.append(note)

    def set_context(self, key: str, value) -> None:
        if value is not None:
            self.context[key] = value

    def get_context(self) -> dict:
        return dict(self.context)

    def get_goal(self) -> str:
        return self.goal

    def get_plan(self) -> list[str]:
        return list(self.plan)

    def get_notes(self) -> list[str]:
        return list(self.notes)

    def render(self) -> str:
        """Safe text representation injected into the agent context."""
        parts = []

        if self.goal:
            parts.append(f"Active goal: {self.goal}")

        if self.plan:
            parts.append("Plan:\n" + "\n".join(
                f"- {step}" for step in self.plan[-5:]
            ))

        if self.notes:
            parts.append("Notes:\n" + "\n".join(
                f"- {note}" for note in self.notes[-8:]
            ))

        if self.context:
            parts.append(
                "Working state:\n" +
                "\n".join(f"- {key}: {value}" for key, value in self.context.items())
            )

        return "\n".join(parts)

    def reset(self) -> None:
        self.goal = ""
        self.plan = []
        self.notes = []
        self.context = {}
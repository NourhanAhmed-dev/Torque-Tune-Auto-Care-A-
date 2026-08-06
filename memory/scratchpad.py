class Scratchpad:
    """
    Temporary working memory for the current task.
    """

    def __init__(self):
        self.reset()

    def set_goal(self, goal):
        self.goal = goal

    def add_step(self, step):
        self.plan.append(step)

    def add_note(self, note):
        self.notes.append(note)

    def set_context(self, key, value):
        self.context[key] = value

    def get_context(self):
        return self.context

    def get_goal(self):
        return self.goal

    def get_plan(self):
        return self.plan

    def get_notes(self):
        return self.notes

    def reset(self):
        self.goal = ""
        self.plan = []
        self.notes = []
        self.context = {}
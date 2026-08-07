from .schema import Message, Transcript, TurnType
from dataclasses import replace
from .utils import count_tokens

MASK_TEXT = "[tool output omitted - was {n} tokens]"


def prune(transcript: Transcript, keep_last_n_tool_outputs: int = 3) -> Transcript:
    """Mask every tool_result except the most recent N — this is the one that wins when
    your bloat is JSON tool payloads rather than conversation, per the lab's worked example."""
    tool_indices = [i for i, m in enumerate(transcript) if m.role == TurnType.TOOL_RESULT]
    keep_set = set(tool_indices[-keep_last_n_tool_outputs:] if keep_last_n_tool_outputs > 0 else []) 

    out = []
    for i, m in enumerate(transcript):
        if m.role == TurnType.TOOL_RESULT and i not in keep_set and not m.pinned:
            out.append(replace(m, content=MASK_TEXT.format(n=count_tokens(m.content))))
        else:
            out.append(m)
    return out
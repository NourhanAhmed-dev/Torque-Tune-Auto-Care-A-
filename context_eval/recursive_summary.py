from typing import Callable, Optional
from .schema import Message, Transcript, TurnType
from itertools import groupby


def _naive_summarizer(chunk: Transcript) -> str:
    facts = [m.content for m in chunk if m.role in (TurnType.USER, TurnType.ASSISTANT)]
    return "auto-summary (no LLM yet): " + " | ".join(facts[:5])



def prune(transcript: Transcript, chunk_size: int = 15,
          summarizer: Optional[Callable[[Transcript], str]] = None) -> Transcript:
    summarizer = summarizer or _naive_summarizer
    pinned = [m for m in transcript if m.pinned]
    rest = [m for m in transcript if not m.pinned]

    turns = [list(g) for _, g in groupby(rest, key=lambda m: m.turn_id)]

    out = []
    for i in range(0, len(turns), chunk_size):
        group = turns[i:i + chunk_size]
        if i + chunk_size >= len(turns):        
            for t in group:
                out.extend(t)
        else:
            flat = [m for t in group for m in t]
            out.append(Message(
                turn_id=flat[0].turn_id,
                seq=flat[0].seq,                  
                role=TurnType.SUMMARY,
                content=summarizer(flat),
            ))
    return sorted(pinned + out, key=lambda m: m.seq)


def gemini_summarizer(client, model: str = "gemini-3.5-flash-lite"):
    """Factory: returns a summarizer(chunk) -> str backed by your real Gemini client.
    Wire this in once memory/ exposes a client you can reuse — don't spin up a second one."""
    def _summarize(chunk: Transcript) -> str:
        text = "\n".join(f"[{m.role.value}] {m.content}" for m in chunk)
        prompt = f"Summarize the key facts and decisions in this excerpt in 1-3 sentences:\n{text}"
        response = client.models.generate_content(model=model, contents=prompt)
        return response.text.strip()
    return _summarize
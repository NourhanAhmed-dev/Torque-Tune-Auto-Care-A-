"""Shared helpers for context_eval.

IMPORTANT: every token number in this package (mask texts, the comparison
table, the README) must come from count_tokens() so the demo and the table agree.
"""
import time

import tiktoken
_ENC = tiktoken.get_encoding("cl100k_base")

def count_tokens(text: str) -> int:
    return len(_ENC.encode(text or ""))



def transcript_tokens(transcript) -> int:
    """Input tokens a run would cost: sum of every message's content."""
    return sum(count_tokens(m.content) for m in transcript)


def timed(fn, *args, **kwargs):
    """Run fn and return (result, elapsed_seconds) — for the latency column."""
    t0 = time.perf_counter()
    result = fn(*args, **kwargs)
    return result, time.perf_counter() - t0
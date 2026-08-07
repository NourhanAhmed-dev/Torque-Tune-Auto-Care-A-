"""Zone-based pruning (4 zones) — the meta-strategy that composes the others.

  1) pinned zone -> always kept whole.
  2) head zone   -> first `head_zone_size` turns compressed into one SUMMARY
                    (recursive-style) so early intake facts survive.
  3) middle zone -> observation masking: only the last `keep_last_n_tool_outputs`
                    tool results stay verbatim, older ones masked.
  4) recent zone -> last `recent_zone_size` turns kept verbatim.
Everything else is dropped. The table decides whether this complexity earns its keep.
"""
from dataclasses import replace
from itertools import groupby
from typing import Callable, Optional

from .observation_masking import MASK_TEXT
from .recursive_summary import _naive_summarizer
from .schema import Message, Transcript, TurnType
from .utils import count_tokens


def prune(
    transcript: Transcript,
    head_zone_size: int = 6,
    recent_zone_size: int = 8,
    keep_last_n_tool_outputs: int = 2,
    summarizer: Optional[Callable[[Transcript], str]] = None,
) -> Transcript:
    summarizer = summarizer or _naive_summarizer

    pinned = [m for m in transcript if m.pinned]
    rest = [m for m in transcript if not m.pinned]
    turns = [list(g) for _, g in groupby(rest, key=lambda m: m.turn_id)]

    h = min(head_zone_size, len(turns))
    r = min(recent_zone_size, len(turns) - h)
    head = [m for t in turns[:h] for m in t]
    middle = [m for t in turns[h:len(turns) - r] for m in t] if r else [m for t in turns[h:] for m in t]
    recent = [m for t in turns[len(turns) - r:] for m in t] if r else []

    out = list(pinned)

    # Zone 2 — head: compress, don't drop (early intake facts live here)
    if head:
        out.append(Message(
            turn_id=head[0].turn_id,
            role=TurnType.SUMMARY,
            content=summarizer(head),
            seq=head[0].seq,
        ))

    # Zone 3 — middle: observation masking on tool outputs
    tool_idx = [i for i, m in enumerate(middle) if m.role == TurnType.TOOL_RESULT]
    keep = set(tool_idx[-keep_last_n_tool_outputs:] if keep_last_n_tool_outputs > 0 else [])
    out += [
        m if not (m.role == TurnType.TOOL_RESULT and i not in keep)
        else replace(m, content=MASK_TEXT.format(n=count_tokens(m.content)))
        for i, m in enumerate(middle)
    ]

    # Zone 4 — recent: verbatim
    out += recent

    return sorted(out, key=lambda m: m.seq)
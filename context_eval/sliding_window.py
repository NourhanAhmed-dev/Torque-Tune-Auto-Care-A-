from .schema import Transcript


def prune(transcript: Transcript, window_size: int = 10) -> Transcript:
    pinned = [m for m in transcript if m.pinned]
    rest = [m for m in transcript if not m.pinned]

    last_turns = set(sorted({m.turn_id for m in rest})[-window_size:])
    kept = [m for m in rest if m.turn_id in last_turns]

    return sorted(pinned + kept, key=lambda m: m.seq)
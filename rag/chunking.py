from __future__ import annotations
import re
from dataclasses import dataclass, field
from pathlib import Path

from rag import config as cfg


def approx_tokens(text: str) -> int:
    return max(1, round(len(text.split()) * 1.3))


@dataclass
class Chunk:
    doc_id: str
    chunk_index: int
    text: str
    token_count: int
    metadata: dict = field(default_factory=dict)


def _parse_frontmatter(raw: str) -> tuple[dict, str]:
    if not raw.startswith("---"):
        return {}, raw
    end = raw.find("\n---", 3)
    if end == -1:
        return {}, raw
    fm_block = raw[3:end].strip()
    body = raw[end + 4:].lstrip("\n")
    meta = {}
    for line in fm_block.splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        v = v.strip()
        if v == "null":
            v = ""
        meta[k.strip()] = v
    return meta, body


def _split_sections(body: str) -> list[str]:
    parts = re.split(r"\n(?=## )", body)
    return [p.strip() for p in parts if p.strip()]


def _merge_to_target(sections: list[str], target: int, overlap: int) -> list[str]:
    """Greedily merge small sections up to ~target tokens; split any single
    section that's larger than target on its own, with a small token overlap
    carried into the next piece so retrieval doesn't lose context at a cut."""
    chunks: list[str] = []
    buf = ""
    buf_tokens = 0
    for sec in sections:
        sec_tokens = approx_tokens(sec)
        if sec_tokens > target * 1.6:
            if buf:
                chunks.append(buf)
                buf, buf_tokens = "", 0
            words = sec.split()
            step = max(1, int(target / 1.3))
            ov = max(0, int(overlap / 1.3))
            i = 0
            while i < len(words):
                piece = " ".join(words[i:i + step])
                chunks.append(piece)
                i += max(1, step - ov)
            continue
        if buf_tokens + sec_tokens > target and buf:
            chunks.append(buf)
            buf, buf_tokens = sec, sec_tokens
        else:
            buf = (buf + "\n\n" + sec) if buf else sec
            buf_tokens += sec_tokens
    if buf:
        chunks.append(buf)
    return chunks


def chunk_markdown_documents(documents_dir: Path) -> list[Chunk]:
    chunks: list[Chunk] = []
    for path in sorted(documents_dir.rglob("*.md")):
        raw = path.read_text(encoding="utf-8")
        meta, body = _parse_frontmatter(raw)
        meta["source_path"] = str(path.relative_to(documents_dir.parent.parent))
        sections = _split_sections(body) or [body]
        pieces = _merge_to_target(sections, cfg.CHUNK_TARGET_TOKENS, cfg.CHUNK_OVERLAP_TOKENS)
        doc_id = meta.get("doc_id") or path.stem
        for i, piece in enumerate(pieces):
            title_line = body.split("\n", 1)[0].lstrip("# ").strip()
            text_with_title = piece if piece.startswith("#") else f"{title_line}\n{piece}"
            chunks.append(Chunk(
                doc_id=doc_id, chunk_index=i, text=text_with_title,
                token_count=approx_tokens(text_with_title), metadata=dict(meta),
            ))
    return chunks


def build_all_chunks():

    return chunk_markdown_documents(
        cfg.DOCUMENTS_DIR
    )


if __name__ == "__main__":
    cs = build_all_chunks()
    from collections import Counter
    by_type = Counter(c.metadata.get("doc_type") for c in cs)
    print(f"total chunks: {len(cs)}")
    for t, n in by_type.items():
        print(f"  {t}: {n}")
    print("\nsample chunk:")
    print(cs[0].metadata)
    print(cs[0].text[:300])

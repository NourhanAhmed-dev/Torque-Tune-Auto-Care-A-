"""RAG document management.
Any change is followed by a non-destructive re-ingest, so future
retrieval (authorization_check) sees the new content immediately."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# platform/backend/services/resource_service.py -> project root
ROOT = Path(__file__).resolve().parents[3]
DOCS = ROOT / "rag" / "documents"


def _reingest():
    result = subprocess.run(
        [sys.executable, "-m", "rag.ingest"],
        cwd=ROOT, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(f"re-ingest failed: {result.stderr[:400]}")


def _safe_path(filename: str) -> Path:
    target = (DOCS / filename).resolve()
    if not str(target).startswith(str(DOCS.resolve())):
        raise ValueError("path escapes documents directory")
    return target


def list_documents():
    return sorted(
        p.relative_to(DOCS).as_posix() for p in DOCS.rglob("*.md") if p.is_file())


def add_document(filename: str, content: str):
    target = _safe_path(filename)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    _reingest()
    return {"added": filename}


def remove_document(filename: str):
    target = _safe_path(filename)
    if not target.exists():
        raise FileNotFoundError(filename)
    target.unlink()
    _reingest()
    return {"removed": filename}
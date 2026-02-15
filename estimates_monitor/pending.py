"""Pending thread store — save, load, list, and transition thread files.

Each thread is stored as data/pending/<thread_id>.json with:
  thread_id, transcript_id, title, pdf_url, tweets[], status, created_at,
  approved_at, published_at, rejected_at, error, x_post_ids[]
"""
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

PENDING_DIR = Path("data/pending")

VALID_STATUSES = {"pending", "approved", "published", "failed", "rejected"}
# Allowed transitions: from → set of valid targets
_TRANSITIONS = {
    "pending":   {"approved", "rejected"},
    "approved":  {"published", "failed"},
    "failed":    {"approved"},          # allow retry
    "rejected":  set(),                 # terminal
    "published": set(),                 # terminal
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _thread_path(thread_id: str) -> Path:
    return PENDING_DIR / f"{thread_id}.json"


def _read(thread_id: str) -> dict:
    path = _thread_path(thread_id)
    if not path.exists():
        raise FileNotFoundError(f"Thread {thread_id} not found")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write(data: dict):
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    path = _thread_path(data["thread_id"])
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ── Public API ────────────────────────────────────────────────────

def save_thread(
    transcript_id: str,
    title: str,
    pdf_url: Optional[str],
    tweets: List[str],
    thread_id: Optional[str] = None,
) -> dict:
    """Create a new pending thread. Returns the thread data dict."""
    tid = thread_id or uuid.uuid4().hex[:12]
    data = {
        "thread_id": tid,
        "transcript_id": transcript_id,
        "title": title,
        "pdf_url": pdf_url,
        "tweets": tweets,
        "status": "pending",
        "created_at": _now_iso(),
        "approved_at": None,
        "published_at": None,
        "rejected_at": None,
        "error": None,
        "x_post_ids": [],
    }
    _write(data)
    return data


def load_thread(thread_id: str) -> dict:
    """Load a thread by ID."""
    return _read(thread_id)


def list_threads(status: Optional[str] = None) -> List[dict]:
    """List all threads, optionally filtered by status."""
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    threads = []
    for p in sorted(PENDING_DIR.glob("*.json")):
        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if status and data.get("status") != status:
            continue
        threads.append(data)
    return threads


def transition(thread_id: str, new_status: str, **extra) -> dict:
    """Move a thread to a new status. Raises ValueError on invalid transition."""
    data = _read(thread_id)
    current = data["status"]
    allowed = _TRANSITIONS.get(current, set())
    if new_status not in allowed:
        raise ValueError(f"Cannot transition {thread_id} from '{current}' to '{new_status}' (allowed: {allowed or 'none'})")
    data["status"] = new_status
    ts = _now_iso()
    if new_status == "approved":
        data["approved_at"] = ts
    elif new_status == "published":
        data["published_at"] = ts
    elif new_status == "rejected":
        data["rejected_at"] = ts
    elif new_status == "failed":
        data["error"] = extra.get("error")
    # Merge any extra fields (e.g. x_post_ids)
    for k, v in extra.items():
        if k in data:
            data[k] = v
    _write(data)
    return data


def approve(thread_id: str) -> dict:
    return transition(thread_id, "approved")


def reject(thread_id: str) -> dict:
    return transition(thread_id, "rejected")


def mark_published(thread_id: str, x_post_ids: List[str]) -> dict:
    return transition(thread_id, "published", x_post_ids=x_post_ids)


def mark_failed(thread_id: str, error: str) -> dict:
    return transition(thread_id, "failed", error=error)

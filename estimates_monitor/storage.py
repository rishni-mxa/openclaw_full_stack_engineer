import json
from pathlib import Path
import tempfile

STATE_PATH = Path("data/state.json")


def load_state():
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not STATE_PATH.exists():
        return {"seen": {}, "posted": {}}
    with STATE_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_state(state: dict):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    # atomic-ish write: write to temp file then rename
    tmp_fd, tmp_path = tempfile.mkstemp(prefix="state", dir=str(STATE_PATH.parent))
    with open(tmp_fd, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    Path(tmp_path).replace(STATE_PATH)


def mark_seen(id: str, meta: dict):
    state = load_state()
    state.setdefault("seen", {})[id] = {
        "first_seen_at": meta.get("first_seen_at"),
        "title": meta.get("title"),
        "pdf_url": meta.get("pdf_url"),
        "published_date": meta.get("published_date"),
        "status": meta.get("status"),
        "downloaded_at": meta.get("downloaded_at"),
        "parsed_at": meta.get("parsed_at"),
        "thread_generated_at": meta.get("thread_generated_at"),
        "pdf_path": meta.get("pdf_path"),
        "pdf_sha256": meta.get("pdf_sha256"),
        "pdf_bytes": meta.get("pdf_bytes"),
    }
    save_state(state)


def update_seen(id: str, updates: dict):
    state = load_state()
    current = state.setdefault("seen", {}).get(id, {})
    current.update(updates)
    state["seen"][id] = current
    save_state(state)


def get_seen(id: str):
    state = load_state()
    return state.get("seen", {}).get(id)


def is_seen(id: str) -> bool:
    state = load_state()
    return id in state.get("seen", {})


def is_posted(id: str) -> bool:
    state = load_state()
    return id in state.get("posted", {})


def mark_posted(id: str, root_id: str, post_ids: list):
    state = load_state()
    state.setdefault("posted", {})[id] = {
        "posted_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "x_thread_root_id": root_id,
        "x_thread_post_ids": post_ids,
    }
    save_state(state)

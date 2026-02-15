"""Tests for X client: mock posting, thread creation, partial failure, resume, idempotency."""
import json
import pytest
from estimates_monitor import pending, storage
from estimates_monitor.x_client import PostResult, create_thread, publish_thread
from estimates_monitor.cli import run_publish


@pytest.fixture(autouse=True)
def tmp_dirs(tmp_path, monkeypatch):
    """Redirect pending store and state.json to temp dirs."""
    monkeypatch.setattr(pending, "PENDING_DIR", tmp_path / "pending")
    monkeypatch.setattr(storage, "STATE_PATH", tmp_path / "state.json")


# ── Helpers ───────────────────────────────────────────────────────

_post_counter = 0


def _mock_post(text: str, reply_to_id=None) -> PostResult:
    global _post_counter
    _post_counter += 1
    return PostResult(post_id=f"post_{_post_counter}", text=text)


def _reset_counter():
    global _post_counter
    _post_counter = 0


@pytest.fixture(autouse=True)
def reset():
    _reset_counter()


# ── create_thread ─────────────────────────────────────────────────

def test_create_thread_posts_in_order():
    results = create_thread(["First", "Second", "Third"], _mock_post)
    assert len(results) == 3
    assert results[0].text == "First"
    assert results[2].text == "Third"
    # Each gets a unique post_id
    ids = [r.post_id for r in results]
    assert len(set(ids)) == 3


def test_create_thread_empty_raises():
    with pytest.raises(ValueError, match="No tweets"):
        create_thread([], _mock_post)


def test_create_thread_reply_chain():
    """Verify reply_to_id is passed correctly (root gets None, rest get previous ID)."""
    calls = []

    def _tracking_post(text, reply_to_id=None):
        calls.append({"text": text, "reply_to": reply_to_id})
        return PostResult(post_id=f"id_{len(calls)}", text=text)

    create_thread(["A", "B", "C"], _tracking_post)
    assert calls[0]["reply_to"] is None
    assert calls[1]["reply_to"] == "id_1"
    assert calls[2]["reply_to"] == "id_2"


# ── publish_thread ────────────────────────────────────────────────

def test_publish_approved_thread():
    pending.save_thread("t1", "Title", "http://pdf", ["T1", "T2"], thread_id="pub1")
    pending.approve("pub1")
    result = publish_thread("pub1", _mock_post)
    assert result["status"] == "published"
    assert len(result["x_post_ids"]) == 2
    # Pending store updated
    thread = pending.load_thread("pub1")
    assert thread["status"] == "published"
    assert thread["published_at"] is not None
    # State.json updated
    assert storage.is_posted("t1")


def test_publish_idempotent():
    pending.save_thread("t2", "Title", "http://pdf", ["T1"], thread_id="pub2")
    pending.approve("pub2")
    publish_thread("pub2", _mock_post)
    # Publish again — should be idempotent
    result = publish_thread("pub2", _mock_post)
    assert result["status"] == "already_published"


def test_publish_pending_raises():
    pending.save_thread("t3", "Title", "http://pdf", ["T1"], thread_id="pub3")
    with pytest.raises(ValueError, match="must be 'approved'"):
        publish_thread("pub3", _mock_post)


def test_publish_rejected_raises():
    pending.save_thread("t4", "Title", "http://pdf", ["T1"], thread_id="pub4")
    pending.reject("pub4")
    with pytest.raises(ValueError, match="must be 'approved'"):
        publish_thread("pub4", _mock_post)


# ── Partial failure + resume ──────────────────────────────────────

def test_partial_failure_records_progress():
    call_count = 0

    def _fail_on_third(text, reply_to_id=None):
        nonlocal call_count
        call_count += 1
        if call_count == 3:
            raise RuntimeError("API timeout")
        return PostResult(post_id=f"ok_{call_count}", text=text)

    pending.save_thread("t5", "Title", "http://pdf", ["A", "B", "C", "D"], thread_id="fail1")
    pending.approve("fail1")
    result = publish_thread("fail1", _fail_on_third)
    assert result["status"] == "failed"
    assert result["x_post_ids"] == ["ok_1", "ok_2"]  # 2 succeeded before failure
    assert result["tweets_remaining"] == 2
    # Thread is now "failed" with partial x_post_ids
    thread = pending.load_thread("fail1")
    assert thread["status"] == "failed"
    assert thread["x_post_ids"] == ["ok_1", "ok_2"]


def test_resume_after_failure():
    # Set up a failed thread with 2 of 4 tweets posted
    pending.save_thread("t6", "Title", "http://pdf", ["A", "B", "C", "D"], thread_id="resume1")
    pending.approve("resume1")

    call_count = 0

    def _fail_on_third(text, reply_to_id=None):
        nonlocal call_count
        call_count += 1
        if call_count == 3:
            raise RuntimeError("API error")
        return PostResult(post_id=f"r_{call_count}", text=text)

    # First attempt: 2 succeed, 3rd fails
    publish_thread("resume1", _fail_on_third)
    thread = pending.load_thread("resume1")
    assert thread["status"] == "failed"
    assert thread["x_post_ids"] == ["r_1", "r_2"]

    # Re-approve for retry
    pending.approve("resume1")

    # Second attempt: should resume from tweet 3
    resume_calls = []

    def _succeed_all(text, reply_to_id=None):
        resume_calls.append({"text": text, "reply_to": reply_to_id})
        return PostResult(post_id=f"new_{len(resume_calls)}", text=text)

    result = publish_thread("resume1", _succeed_all)
    assert result["status"] == "published"
    # Should only have posted tweets C and D (indices 2,3)
    assert len(resume_calls) == 2
    assert resume_calls[0]["text"] == "C"
    assert resume_calls[0]["reply_to"] == "r_2"  # replies to last successful
    # All 4 IDs recorded
    assert result["x_post_ids"] == ["r_1", "r_2", "new_1", "new_2"]


# ── CLI publish command ───────────────────────────────────────────

def test_cli_publish():
    pending.save_thread("t7", "Title", "http://pdf", ["T1", "T2"], thread_id="clip1")
    pending.approve("clip1")
    result = run_publish("clip1", post_func=_mock_post)
    assert result["status"] == "published"

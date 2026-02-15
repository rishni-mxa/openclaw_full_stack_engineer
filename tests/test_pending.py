"""Tests for pending thread store and CLI approval commands."""
import json
import pytest
from pathlib import Path
from estimates_monitor import pending
from estimates_monitor.cli import run_status, run_approve, run_reject


@pytest.fixture(autouse=True)
def tmp_pending_dir(tmp_path, monkeypatch):
    """Redirect pending store to a temp directory for each test."""
    monkeypatch.setattr(pending, "PENDING_DIR", tmp_path / "pending")


# ── Pending store ─────────────────────────────────────────────────

def test_save_and_load():
    data = pending.save_thread(
        transcript_id="https://example.com/t1",
        title="Test Committee 2026-02-10",
        pdf_url="https://example.com/t1.pdf",
        tweets=["Tweet one", "Tweet two"],
        thread_id="abc123",
    )
    assert data["thread_id"] == "abc123"
    assert data["status"] == "pending"
    assert len(data["tweets"]) == 2

    loaded = pending.load_thread("abc123")
    assert loaded == data


def test_list_threads_all():
    pending.save_thread("t1", "Title 1", None, ["a"], thread_id="id1")
    pending.save_thread("t2", "Title 2", None, ["b"], thread_id="id2")
    threads = pending.list_threads()
    assert len(threads) == 2


def test_list_threads_filtered():
    pending.save_thread("t1", "Title 1", None, ["a"], thread_id="id1")
    pending.save_thread("t2", "Title 2", None, ["b"], thread_id="id2")
    pending.approve("id1")
    assert len(pending.list_threads(status="pending")) == 1
    assert len(pending.list_threads(status="approved")) == 1


def test_not_found_raises():
    with pytest.raises(FileNotFoundError):
        pending.load_thread("nonexistent")


# ── Status transitions ───────────────────────────────────────────

def test_approve_sets_status():
    pending.save_thread("t1", "T", None, ["a"], thread_id="tx1")
    result = pending.approve("tx1")
    assert result["status"] == "approved"
    assert result["approved_at"] is not None


def test_reject_sets_status():
    pending.save_thread("t1", "T", None, ["a"], thread_id="tx2")
    result = pending.reject("tx2")
    assert result["status"] == "rejected"
    assert result["rejected_at"] is not None


def test_mark_published():
    pending.save_thread("t1", "T", None, ["a"], thread_id="tx3")
    pending.approve("tx3")
    result = pending.mark_published("tx3", x_post_ids=["111", "222"])
    assert result["status"] == "published"
    assert result["x_post_ids"] == ["111", "222"]
    assert result["published_at"] is not None


def test_mark_failed_and_retry():
    pending.save_thread("t1", "T", None, ["a"], thread_id="tx4")
    pending.approve("tx4")
    failed = pending.mark_failed("tx4", error="API timeout")
    assert failed["status"] == "failed"
    assert failed["error"] == "API timeout"
    # Can retry: failed → approved
    retried = pending.approve("tx4")
    assert retried["status"] == "approved"


def test_invalid_transition_raises():
    pending.save_thread("t1", "T", None, ["a"], thread_id="tx5")
    pending.reject("tx5")
    with pytest.raises(ValueError, match="Cannot transition"):
        pending.approve("tx5")  # rejected is terminal


def test_published_is_terminal():
    pending.save_thread("t1", "T", None, ["a"], thread_id="tx6")
    pending.approve("tx6")
    pending.mark_published("tx6", x_post_ids=["111"])
    with pytest.raises(ValueError, match="Cannot transition"):
        pending.reject("tx6")


def test_cannot_skip_approve():
    pending.save_thread("t1", "T", None, ["a"], thread_id="tx7")
    with pytest.raises(ValueError, match="Cannot transition"):
        pending.mark_published("tx7", x_post_ids=["111"])  # pending → published not allowed


# ── CLI commands ──────────────────────────────────────────────────

def test_cli_status_lists_threads():
    pending.save_thread("t1", "Title A", None, ["a", "b"], thread_id="s1")
    pending.save_thread("t2", "Title B", None, ["c"], thread_id="s2")
    result = run_status()
    assert len(result) == 2
    assert result[0]["thread_id"] == "s1"
    assert result[0]["tweets"] == 2


def test_cli_status_filter():
    pending.save_thread("t1", "Title A", None, ["a"], thread_id="f1")
    pending.save_thread("t2", "Title B", None, ["b"], thread_id="f2")
    pending.approve("f1")
    result = run_status(status_filter="approved")
    assert len(result) == 1
    assert result[0]["thread_id"] == "f1"


def test_cli_approve():
    pending.save_thread("t1", "T", None, ["a"], thread_id="a1")
    result = run_approve("a1")
    assert result["status"] == "approved"


def test_cli_approve_dry_run():
    pending.save_thread("t1", "T", None, ["Tweet one!", "Tweet two!"], thread_id="d1")
    result = run_approve("d1", dry_run=True)
    assert result["dry_run"] is True
    assert len(result["payloads"]) == 2
    assert result["payloads"][0]["text"] == "Tweet one!"
    assert result["payloads"][0]["chars"] == 10
    # Status should NOT change
    thread = pending.load_thread("d1")
    assert thread["status"] == "pending"


def test_cli_reject():
    pending.save_thread("t1", "T", None, ["a"], thread_id="r1")
    result = run_reject("r1")
    assert result["status"] == "rejected"

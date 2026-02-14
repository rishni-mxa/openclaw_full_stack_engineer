import hashlib
from datetime import datetime
from pathlib import Path
from estimates_monitor import cli, schedule, storage, downloader


class DummyResp:
    def __init__(self, data: bytes):
        self.data = data
    def raise_for_status(self):
        return
    def iter_content(self, chunk_size=8192):
        yield self.data


class DummySession:
    def __init__(self, data: bytes):
        self.data = data
        self.calls = 0
    def get(self, url, stream=True, timeout=30):
        self.calls += 1
        return DummyResp(self.data)


def test_download_latest_writes_file_and_updates_state(tmp_path, monkeypatch):
    entry = schedule.TranscriptEntry(
        title="Estimates hearing 9",
        page_url="https://example.org/transcripts/est9.html",
        pdf_url="https://example.org/downloads/est9.pdf",
        published_date=datetime(2026, 2, 13, 9, 0, 0),
        status="Published in full",
    )
    monkeypatch.setattr(cli.schedule, "get_latest_published", lambda session=None, is_seen_func=None: entry)
    monkeypatch.setattr(storage, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(downloader, "PDF_DIR", tmp_path / "pdfs")

    data = b"%PDF-1.4 mock data"
    session = DummySession(data)

    result = cli.run_download_latest(session=session, now_func=lambda: datetime(2026, 2, 13, 10, 30, 0))

    expected_hash = hashlib.sha256(data).hexdigest()
    assert result["pdf_sha256"] == expected_hash
    assert result["pdf_bytes"] == len(data)
    assert Path(result["pdf_path"]).exists()

    state = storage.load_state()
    seen = state["seen"][entry.page_url]
    assert seen["pdf_sha256"] == expected_hash
    assert seen["pdf_bytes"] == len(data)
    assert seen["pdf_path"] == result["pdf_path"]


def test_download_latest_idempotent_without_force(tmp_path, monkeypatch):
    entry = schedule.TranscriptEntry(
        title="Estimates hearing 10",
        page_url="https://example.org/transcripts/est10.html",
        pdf_url="https://example.org/downloads/est10.pdf",
        published_date=None,
        status="Published in full",
    )
    monkeypatch.setattr(cli.schedule, "get_latest_published", lambda session=None, is_seen_func=None: entry)
    monkeypatch.setattr(storage, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(downloader, "PDF_DIR", tmp_path / "pdfs")

    data = b"%PDF-1.4 data"
    session = DummySession(data)

    first = cli.run_download_latest(session=session, now_func=lambda: datetime(2026, 2, 13, 10, 30, 0))
    second = cli.run_download_latest(session=session, now_func=lambda: datetime(2026, 2, 13, 10, 31, 0))

    assert session.calls == 1
    assert second["skipped"] is True
    assert second["pdf_path"] == first["pdf_path"]


def test_download_latest_refuses_if_posted(tmp_path, monkeypatch):
    entry = schedule.TranscriptEntry(
        title="Estimates hearing 11",
        page_url="https://example.org/transcripts/est11.html",
        pdf_url="https://example.org/downloads/est11.pdf",
        published_date=None,
        status="Published in full",
    )
    monkeypatch.setattr(cli.schedule, "get_latest_published", lambda session=None, is_seen_func=None: entry)
    monkeypatch.setattr(storage, "STATE_PATH", tmp_path / "state.json")
    storage.mark_posted(entry.page_url, "root", [])
    try:
        cli.run_download_latest()
        assert False, "Expected SystemExit"
    except SystemExit as e:
        assert e.code == 2


def test_download_latest_dry_run_resolves_without_download(tmp_path, monkeypatch):
    entry = schedule.TranscriptEntry(
        title="Estimates hearing DR",
        page_url="https://example.org/transcripts/est-dr.html",
        pdf_url="https://example.org/downloads/est-dr.pdf",
        published_date=datetime(2026, 2, 13, 9, 0, 0),
        status="Published in full",
        pdf_fallback_committee=None,
    )
    monkeypatch.setattr(cli.schedule, "get_latest_published", lambda session=None, is_seen_func=None: entry)
    monkeypatch.setattr(storage, "STATE_PATH", tmp_path / "state.json")
    # Ensure downloader would raise if called
    monkeypatch.setattr(downloader, "download_pdf_deterministic", lambda *a, **k: (_ for _ in ()).throw(AssertionError("download called during dry-run")))

    result = cli.run_download_latest(session=None, now_func=lambda: datetime(2026, 2, 13, 10, 30, 0), dry_run=True)
    assert result["pdf_url"] == entry.pdf_url
    # State must not have been mutated
    state = storage.load_state()
    assert state.get("seen") is None or entry.page_url not in state.get("seen", {})

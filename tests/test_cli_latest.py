from datetime import datetime
from estimates_monitor import cli, schedule, storage


def test_run_latest_marks_seen(tmp_path, monkeypatch):
    entry = schedule.TranscriptEntry(
        title="Estimates hearing 9",
        page_url="https://example.org/transcripts/est9.html",
        pdf_url="https://example.org/downloads/est9.pdf",
        published_date=datetime(2026, 2, 13, 9, 0, 0),
        status="Published in full",
    )

    def fake_get_latest(session=None, is_seen_func=None):
        return entry

    monkeypatch.setattr(cli.schedule, "get_latest_published", fake_get_latest)
    monkeypatch.setattr(storage, "STATE_PATH", tmp_path / "state.json")

    result = cli.run_latest(now_func=lambda: datetime(2026, 2, 13, 10, 30, 0))

    assert result["id"] == entry.page_url
    assert result["pdf_url"] == entry.pdf_url
    state = storage.load_state()
    assert entry.page_url in state["seen"]
    assert state["seen"][entry.page_url]["title"] == entry.title
    assert state["seen"][entry.page_url]["published_date"] == entry.published_date.isoformat()

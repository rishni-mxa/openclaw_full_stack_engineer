from pathlib import Path
import requests

from estimates_monitor import downloader


class DummyResp:
    def __init__(self, status_code: int):
        self.status_code = status_code

    def raise_for_status(self):
        raise requests.HTTPError(response=self)


class DummySession:
    def __init__(self):
        self.calls = 0

    def get(self, url, stream=True, timeout=30):
        self.calls += 1
        return DummyResp(status_code=403)


def test_download_pdf_deterministic_uses_playwright_on_403(tmp_path, monkeypatch):
    # Force requests path to 403
    sess = DummySession()

    # Mock playwright byte fetcher
    monkeypatch.setattr(
        downloader,
        "_download_pdf_bytes_with_playwright",
        lambda url, profile_dir, timeout_ms=60000, referer_url=None, verbose=False: b"%PDF-1.4 mocked pdf bytes",
    )

    out = downloader.download_pdf_deterministic(
        "https://parlinfo.aph.gov.au/parlInfo/download/x.pdf#frag",
        base_name="test",
        session=sess,
        out_dir=tmp_path,
        playwright_profile_dir=tmp_path / "profile",
        verbose=True,
    )

    assert sess.calls == 1
    assert Path(out["path"]).exists()
    assert out["bytes"] > 0
    assert out["sha256"]

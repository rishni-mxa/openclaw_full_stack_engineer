"""Test that downloader raises on 403 (WAF bypass is now handled by OpenClaw agent)."""

from pathlib import Path
import pytest
import requests

from estimates_monitor import downloader


class DummyResp:
    def __init__(self, status_code: int):
        self.status_code = status_code

    def raise_for_status(self):
        exc = requests.HTTPError(response=self)
        exc.response = self
        raise exc


class DummySession:
    def __init__(self):
        self.calls = 0

    def get(self, url, stream=True, timeout=30):
        self.calls += 1
        return DummyResp(status_code=403)


def test_download_pdf_deterministic_raises_on_403(tmp_path):
    """When ParlInfo returns 403, downloader should raise rather than
    attempting its own browser fallback.  The OpenClaw agent handles WAF bypass."""
    sess = DummySession()

    with pytest.raises(Exception):
        downloader.download_pdf_deterministic(
            "https://parlinfo.aph.gov.au/parlInfo/download/x.pdf#frag",
            base_name="test",
            session=sess,
            out_dir=tmp_path,
        )

    assert sess.calls == 1

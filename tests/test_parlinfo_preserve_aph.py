from estimates_monitor import parlinfo, downloader
from pathlib import Path
import hashlib


def test_parlinfo_preserves_aph_host_and_downloader_works(tmp_path, monkeypatch):
    display_url = "https://parlinfo.aph.gov.au/display/display.w3p;query=Id:\"committees/estimate/29366/0001\""
    # HTML contains an aph.gov.au media link (committee fallback)
    html = '<a href="https://www.aph.gov.au/-/media/Estimates/fpa/add2526/FPA.pdf">Download PDF</a>'
    pdf = parlinfo.extract_pdf_url(display_url, html)
    assert pdf.startswith("https://www.aph.gov.au/-/media/")

    # Now ensure downloader can fetch it (mock session)
    data = b"%PDF-1.4 mock"
    class DummyResp:
        def __init__(self, data):
            self.data = data
        def raise_for_status(self):
            return
        def iter_content(self, chunk_size=8192):
            yield self.data
    class DummySession:
        def __init__(self, data):
            self.data = data
        def get(self, url, stream=True, timeout=30):
            assert url == pdf
            return DummyResp(self.data)
    monkeypatch.setattr(downloader, "PDF_DIR", tmp_path / "pdfs")
    sess = DummySession(data)
    out = downloader.download_pdf_deterministic(pdf, "name", session=sess)
    assert Path(out["path"]).exists()
    assert out["sha256"] == hashlib.sha256(data).hexdigest()

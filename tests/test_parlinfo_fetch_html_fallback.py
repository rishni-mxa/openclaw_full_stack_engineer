from estimates_monitor import schedule
from types import SimpleNamespace

# Use the captured fixture specific to 29366
with open('fixtures/detail_29366.html','r', encoding='utf-8') as f:
    FIXTURE_HTML = f.read()


def test_403_triggers_fetch_html_fallback(monkeypatch):
    # Prepare schedule HTML that references a ParlInfo display page
    schedule_html = '''
    <html><body><table><tbody>
      <tr>
        <td>10/02/2026</td>
        <td><a href="/committee/rra">Rural and Regional Affairs</a></td>
        <td>29366</td>
        <td><a href="https://parlinfo.aph.gov.au/parlInfo/search/display/display.w3p;query=Id:%22committees/estimate/29366/0002%22">Published in full</a></td>
      </tr>
    </tbody></table></body></html>
    '''

    parlinfo_display_url = "https://parlinfo.aph.gov.au/parlInfo/search/display/display.w3p;query=Id:%22committees/estimate/29366/0002%22"

    class DummyResp(SimpleNamespace):
        def raise_for_status(self):
            if getattr(self, 'status_code', 200) >= 400:
                raise Exception(str(self.status_code))

    class DummySession:
        def __init__(self, mapping):
            self.mapping = mapping
            self.calls = []

        def get(self, url, **kwargs):
            self.calls.append(url)
            return self.mapping[url]

    sess = DummySession({
        "https://example.org": DummyResp(url="https://example.org", text=schedule_html, status_code=200),
        parlinfo_display_url: DummyResp(url=parlinfo_display_url, text="", status_code=403),
    })

    # Monkeypatch the SCHEDULE_URL_CANDIDATES to our example and patch fetch_html to return the fixture
    orig = schedule.SCHEDULE_URL_CANDIDATES
    schedule.SCHEDULE_URL_CANDIDATES = ["https://example.org"]
    try:
        # Patch fetcher.fetch_html to return the captured fixture HTML when called for parlinfo_display_url
        import estimates_monitor.fetcher as fetcher

        def fake_fetch_html(url, session=None):
            assert url == parlinfo_display_url
            return FIXTURE_HTML

        monkeypatch.setattr(fetcher, 'fetch_html', fake_fetch_html)

        latest = schedule.get_latest_published(session=sess)
    finally:
        schedule.SCHEDULE_URL_CANDIDATES = orig

    assert latest is not None
    assert latest.pdf_fallback_committee is False
    assert latest.pdf_url is not None
    assert 'toc_pdf' in latest.pdf_url

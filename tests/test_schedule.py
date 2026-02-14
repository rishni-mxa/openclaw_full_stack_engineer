from estimates_monitor import schedule
from pathlib import Path
import requests

class DummySession:
    def __init__(self, mapping):
        self.mapping = mapping
    def get(self, url, **kwargs):
        class R:
            def __init__(self, url, text):
                self.url = url
                self.text = text
                self.status_code = 200
            def raise_for_status(self):
                return
        return R(url, self.mapping[url])


def test_parse_schedule_fixture():
    html = Path('fixtures/schedule.html').read_text(encoding='utf-8')
    entries = schedule._parse_schedule_html(html, base_url='https://example.org')
    # two published rows; draft should be ignored
    assert len(entries) == 2
    # ensure we pick the transcript-cell link (parlinfo), not the committee landing page
    assert any('parlinfo.aph.gov.au' in e.page_url for e in entries)
    titles = [e.title for e in entries]
    assert 'Finance and Public Administration' in titles


def test_get_latest_published_resolves_pdf_from_detail(tmp_path):
    sched = Path('fixtures/schedule.html').read_text(encoding='utf-8')
    detail = Path('fixtures/detail.html').read_text(encoding='utf-8')
    orig_candidates = schedule.SCHEDULE_URL_CANDIDATES
    schedule.SCHEDULE_URL_CANDIDATES = ["https://example.org"]
    mapping = {
        "https://example.org": sched,
        'https://parlinfo.aph.gov.au/parlInfo/search/display/display.w3p;query=Id:%22committees/estimate/11111/0000%22': detail,
    }
    session = DummySession(mapping)
    try:
        latest = schedule.get_latest_published(session=session)
    finally:
        schedule.SCHEDULE_URL_CANDIDATES = orig_candidates
    assert latest is not None
    assert latest.pdf_url is not None
    assert latest.page_url.startswith('https://parlinfo.aph.gov.au/')
    assert latest.committee_url is not None
    assert latest.pdf_url.endswith('transcript-estimates1.pdf')


def test_fetch_schedule_skips_aph_help_404_and_tries_next_candidate():
    sched = Path('fixtures/schedule.html').read_text(encoding='utf-8')

    class DummyResp:
        def __init__(self, url, text, status_code):
            self.url = url
            self.text = text
            self.status_code = status_code

        def raise_for_status(self):
            if self.status_code >= 400:
                raise requests.HTTPError(f"{self.status_code} for {self.url}")

    class DummySession2:
        def __init__(self):
            self.calls = []

        def get(self, url, **kwargs):
            self.calls.append(url)
            if url == "https://bad.example.org":
                return DummyResp(
                    url="https://www.aph.gov.au/Help/404?item=%2fabout_parliament%2festimates%2ftranscript_schedule",
                    text="<html>not found</html>",
                    status_code=404,
                )
            if url == "https://good.example.org":
                return DummyResp(url=url, text=sched, status_code=200)
            raise KeyError(url)

    orig_candidates = schedule.SCHEDULE_URL_CANDIDATES
    schedule.SCHEDULE_URL_CANDIDATES = ["https://bad.example.org", "https://good.example.org"]
    session = DummySession2()
    try:
        entries = schedule.get_schedule(session=session)
    finally:
        schedule.SCHEDULE_URL_CANDIDATES = orig_candidates

    assert session.calls == ["https://bad.example.org", "https://good.example.org"]
    assert len(entries) == 2

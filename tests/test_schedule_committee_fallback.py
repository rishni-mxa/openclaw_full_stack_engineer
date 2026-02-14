from estimates_monitor import schedule


class DummyResp:
    def __init__(self, url, text, status_code=200):
        self.url = url
        self.text = text
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"{self.status_code}")


class DummySession:
    def __init__(self, mapping):
        self.mapping = mapping
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(url)
        resp = self.mapping[url]
        return resp


def test_committee_fallback_resolves_media_to_aph(monkeypatch):
    # Force fetch_html path to fail so code exercises committee fallback.
    import estimates_monitor.fetcher as fetcher
    monkeypatch.setattr(fetcher, "fetch_html", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("blocked")))
    # Schedule page points to a ParlInfo display page which returns 403; committee page contains '/-/media/...' href
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
    # Note: schedule base will be https://example.org so committee_url resolves relative to that in the parser
    committee_url = "https://example.org/committee/rra"

    parlinfo_resp = DummyResp(parlinfo_display_url, "", status_code=403)
    committee_html = '<html><body><a href="/-/media/Estimates/rrat/add2526/RRAT.pdf">Download</a></body></html>'
    committee_resp = DummyResp(committee_url, committee_html, status_code=200)

    sess = DummySession({
        "https://example.org": DummyResp("https://example.org", schedule_html, 200),
        parlinfo_display_url: parlinfo_resp,
        committee_url: committee_resp,
    })

    orig_candidates = schedule.SCHEDULE_URL_CANDIDATES
    schedule.SCHEDULE_URL_CANDIDATES = ["https://example.org"]
    try:
        latest = schedule.get_latest_published(session=sess)
    finally:
        schedule.SCHEDULE_URL_CANDIDATES = orig_candidates

    assert latest is not None
    assert latest.pdf_fallback_committee is True
    assert latest.pdf_url == 'https://www.aph.gov.au/-/media/Estimates/rrat/add2526/RRAT.pdf'

"""Test that 403 from ParlInfo sets parlinfo_blocked=True and leaves pdf_url=None.

The committee page fallback was removed because it downloads unrelated PDFs
(e.g. committee program instead of transcript).  On 403, the agent handles
browser-based WAF bypass."""

from estimates_monitor import schedule
import requests as _requests


class DummyResp:
    def __init__(self, url, text, status_code=200):
        self.url = url
        self.text = text
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            exc = _requests.exceptions.HTTPError(f"{self.status_code}")
            exc.response = self
            raise exc


class DummySession:
    def __init__(self, mapping):
        self.mapping = mapping
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(url)
        resp = self.mapping[url]
        return resp


def test_403_sets_parlinfo_blocked_and_no_pdf():
    """When ParlInfo returns 403, entry should have parlinfo_blocked=True and pdf_url=None.
    The committee page should NOT be fetched (it has unrelated PDFs)."""
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
    committee_url = "https://example.org/committee/rra"

    parlinfo_resp = DummyResp(parlinfo_display_url, "", status_code=403)

    sess = DummySession({
        "https://example.org": DummyResp("https://example.org", schedule_html, 200),
        parlinfo_display_url: parlinfo_resp,
        # Committee page NOT in mapping — should never be requested
    })

    orig_candidates = schedule.SCHEDULE_URL_CANDIDATES
    schedule.SCHEDULE_URL_CANDIDATES = ["https://example.org"]
    try:
        latest = schedule.get_latest_published(session=sess)
    finally:
        schedule.SCHEDULE_URL_CANDIDATES = orig_candidates

    assert latest is not None
    assert latest.parlinfo_blocked is True
    assert latest.pdf_url is None
    # Verify committee page was NOT fetched
    assert committee_url not in sess.calls

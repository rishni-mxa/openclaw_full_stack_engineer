"""Test that a 403 from ParlInfo sets parlinfo_blocked and leaves pdf_url=None.

Browser-based WAF bypass is handled by the OpenClaw agent, not by the
schedule module.  On 403, schedule.get_latest_published returns immediately
with parlinfo_blocked=True so the agent workflow can use its browser tool.
"""

from estimates_monitor import schedule
from types import SimpleNamespace


def test_403_sets_parlinfo_blocked():
    """When ParlInfo returns 403, entry should have parlinfo_blocked=True, pdf_url=None."""
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
                import requests
                exc = requests.exceptions.HTTPError(str(self.status_code))
                exc.response = self
                raise exc

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
        # No committee page in mapping — should never be requested
    })

    orig = schedule.SCHEDULE_URL_CANDIDATES
    schedule.SCHEDULE_URL_CANDIDATES = ["https://example.org"]
    try:
        latest = schedule.get_latest_published(session=sess)
    finally:
        schedule.SCHEDULE_URL_CANDIDATES = orig

    assert latest is not None
    assert latest.parlinfo_blocked is True
    assert latest.pdf_url is None

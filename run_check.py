from estimates_monitor import schedule

# Test 1
html = '''
<html><body>
<table><tbody>
  <tr>
    <td>10/02/2026</td>
    <td><a href="/committee/a">A Committee</a></td>
    <td>29365</td>
    <td><a href="https://parlinfo.aph.gov.au/parlInfo/search/display/display.w3p;query=Id:%22committees/estimate/29365/0001%22">Published in full</a></td>
  </tr>
  <tr>
    <td>10/02/2026</td>
    <td><a href="/committee/b">B Committee</a></td>
    <td>29366</td>
    <td><a href="https://parlinfo.aph.gov.au/parlInfo/search/display/display.w3p;query=Id:%22committees/estimate/29366/0002%22">Published in full</a></td>
  </tr>
</tbody></table>
</body></html>
'''
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
    def get(self, url, **kwargs):
        return self.mapping[url]

sess = DummySession({
    "https://example.org": DummyResp("https://example.org", html, 200),
    "https://parlinfo.aph.gov.au/parlInfo/search/display/display.w3p;query=Id:%22committees/estimate/29366/0002%22": DummyResp(
        "https://parlinfo.aph.gov.au/parlInfo/search/display/display.w3p;query=Id:%22committees/estimate/29366/0002%22",
        "<html></html>",
        200,
    ),
})
orig = schedule.SCHEDULE_URL_CANDIDATES
schedule.SCHEDULE_URL_CANDIDATES = ["https://example.org"]
try:
    latest = schedule.get_latest_published(session=sess)
    print('Latest page_url:', latest.page_url)
finally:
    schedule.SCHEDULE_URL_CANDIDATES = orig

# Test 2
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
parlinfo_detail = '''
<html><body>
  <a href="https://parlinfo.aph.gov.au/parlInfo/download/committees/estimate/29366/other/WRONG.pdf;fileType=application%2Fpdf">PDF</a>
  <a href="https://parlinfo.aph.gov.au/parlInfo/download/committees/estimate/29366/toc_pdf/RIGHT.pdf;fileType=application%2Fpdf#search=%22committees/estimate/29366/0002%22">Download PDF</a>
</body></html>
'''
sess2 = DummySession({
    "https://example.org": DummyResp("https://example.org", schedule_html, 200),
    "https://parlinfo.aph.gov.au/parlInfo/search/display/display.w3p;query=Id:%22committees/estimate/29366/0002%22": DummyResp(
        "https://parlinfo.aph.gov.au/parlInfo/search/display/display.w3p;query=Id:%22committees/estimate/29366/0002%22",
        parlinfo_detail,
        200,
    ),
})
orig = schedule.SCHEDULE_URL_CANDIDATES
schedule.SCHEDULE_URL_CANDIDATES = ["https://example.org"]
try:
    latest2 = schedule.get_latest_published(session=sess2)
    print('Latest pdf_url:', latest2.pdf_url)
finally:
    schedule.SCHEDULE_URL_CANDIDATES = orig

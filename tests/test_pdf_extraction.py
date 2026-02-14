from estimates_monitor import schedule
from pathlib import Path

def test_detail_fixture_pdf_link():
    detail = Path('fixtures/detail.html').read_text(encoding='utf-8')
    # use _parse to find pdf link
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(detail, 'html.parser')
    a = soup.find('a', href=lambda h: h and h.endswith('.pdf'))
    assert a is not None
    assert a['href'].endswith('transcript-estimates1.pdf')

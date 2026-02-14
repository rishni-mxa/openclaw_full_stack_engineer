from estimates_monitor.parlinfo import extract_pdf_url

EXPECTED = "https://parlinfo.aph.gov.au/parlInfo/download/committees/estimate/29366/toc_pdf/Rural%20and%20Regional%20Affairs%20and%20Transport%20Legislation%20Committee_2026_02_10.pdf;fileType=application%2Fpdf#search=%22committees/estimate/29366/0002%22"


def test_extract_from_fixture():
    display_url = "http://parlinfo.aph.gov.au/parlInfo/search/display/display.w3p;query=Id%3A%22committees%2Festimate%2F29366%2F0002%22"
    # use captured fixture specific to 29366
    with open('fixtures/detail_29366.html','r', encoding='utf-8') as f:
        html = f.read()
    pdf_url = extract_pdf_url(display_url, html)
    assert pdf_url == EXPECTED, f"pdf_url was {pdf_url!r}"

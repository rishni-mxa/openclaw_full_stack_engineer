from urllib.parse import urljoin, urlparse, urlunparse
from bs4 import BeautifulSoup

def _force_https(url):
    p = urlparse(url)
    if p.hostname and p.hostname.endswith('parlinfo.aph.gov.au') and p.scheme != 'https':
        p = p._replace(scheme='https')
        return urlunparse(p)
    return url


def extract_pdf_url(display_url, html_text):
    """Given a ParlInfo display page URL and its HTML, return absolute pdf download URL if found.
    Normalises parlinfo.aph.gov.au links to https.
    Prefers '/toc_pdf/' links when present.
    """
    soup = BeautifulSoup(html_text, "html.parser")
    links = [a['href'] for a in soup.find_all('a', href=True) if a.get('href')]
    # Prefer toc_pdf links
    for href in links:
        if '/toc_pdf/' in href and (href.lower().endswith('.pdf') or 'fileType' in href):
            return _force_https(urljoin(display_url, href))
    # Next prefer explicit download links (parlinfo/download) with pdf
    for href in links:
        if 'download' in href and (href.lower().endswith('.pdf') or 'fileType' in href):
            return _force_https(urljoin(display_url, href))
    # fallback: any pdf link
    for href in links:
        if href.lower().endswith('.pdf'):
            return _force_https(urljoin(display_url, href))
    return None

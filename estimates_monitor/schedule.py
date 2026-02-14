from dataclasses import dataclass
from typing import Optional, List
from bs4 import BeautifulSoup
import requests
from urllib.parse import urljoin, urlparse
from datetime import datetime
import re
import time

from estimates_monitor import parlinfo


@dataclass
class TranscriptEntry:
    title: str
    page_url: str
    pdf_url: Optional[str]
    published_date: Optional[datetime]
    status: str
    committee_url: Optional[str] = None
    ref_no: Optional[int] = None
    # True if we had to fall back to the committee page PDF instead of ParlInfo
    pdf_fallback_committee: bool = False


# Canonical schedule URL (APH has moved this at least once)
SCHEDULE_URL = "https://www.aph.gov.au/Parliamentary_Business/Hansard/Estimates_Transcript_Schedule"
# Fallback candidates for resilience
SCHEDULE_URL_CANDIDATES = [
    SCHEDULE_URL,
    "https://www.aph.gov.au/About_Parliament/Estimates/Transcript_Schedule",
]


def _parse_date(text: str) -> Optional[datetime]:
    if not text:
        return None
    text = text.strip()
    # common formats seen on site: '13 February 2026', '28 Feb 2024', '5 January 2025', '09/02/2025'
    for fmt in ["%d %B %Y", "%d %b %Y", "%d %B %y", "%d/%m/%Y"]:
        try:
            return datetime.strptime(text, fmt)
        except Exception:
            continue
    # fallback: find dd mmm yyyy in text
    m = re.search(r"(\d{1,2}\s+\w+\s+\d{4})", text)
    if m:
        try:
            return datetime.strptime(m.group(1), "%d %B %Y")
        except Exception:
            return None
    return None


def _normalize_status(text: str) -> str:
    if not text:
        return ""
    t = re.sub(r"\s+", " ", text).strip()
    t_lower = t.lower()
    if "published in full" in t_lower:
        return "Published in full"
    if "published" in t_lower:
        return "Published"
    return t


def _parse_schedule_html(html: str, base_url: str = SCHEDULE_URL) -> List[TranscriptEntry]:
    soup = BeautifulSoup(html, "html.parser")
    entries: List[TranscriptEntry] = []
    # Prefer structured rows (table rows, list items); fall back to any links
    containers = []
    for tr in soup.select("table tbody tr"):
        containers.append(tr)
    for li in soup.select("ul li, ol li"):
        containers.append(li)
    if not containers:
        # fallback to any parent of links
        for a in soup.find_all("a", href=True):
            if a.parent:
                containers.append(a.parent)
    seen_links = set()
    for block in containers:
        # Special handling for table rows on the real APH schedule page:
        # the committee link is NOT the transcript link.
        if getattr(block, "name", None) == "tr":
            tds = block.find_all("td")
            if len(tds) >= 3:
                date_text = tds[0].get_text(" ", strip=True)
                published_date = _parse_date(date_text) if date_text else None

                committee_a = tds[1].find("a", href=True)
                committee_url = urljoin(base_url, committee_a["href"]) if committee_a else None
                title = committee_a.get_text(" ", strip=True) if committee_a else tds[1].get_text(" ", strip=True)

                # Ref No column (often numeric like 29366; may have suffix)
                ref_text = tds[2].get_text(" ", strip=True) if len(tds) >= 3 else ""
                m_ref = re.search(r"(\d+)", ref_text or "")
                ref_no = int(m_ref.group(1)) if m_ref else None

                # Transcript column often has link text like "Published in full" to parlinfo
                transcript_a = None
                # Prefer searching only within transcript cell if possible
                transcript_td = tds[-1]
                for a in transcript_td.find_all("a", href=True):
                    txt = a.get_text(" ", strip=True)
                    if "published" in (txt or "").lower():
                        transcript_a = a
                        break
                if not transcript_a:
                    continue

                href = transcript_a["href"]
                if href in seen_links:
                    continue
                seen_links.add(href)

                status = _normalize_status(transcript_a.get_text(" ", strip=True))
                if not (status.lower().startswith("published") or "published" in status.lower()):
                    continue

                page_url = urljoin(base_url, href)
                entries.append(
                    TranscriptEntry(
                        title=title,
                        page_url=page_url,
                        pdf_url=None,
                        published_date=published_date,
                        status=status,
                        committee_url=committee_url,
                        ref_no=ref_no,
                    )
                )
                continue

        # Generic fallback for older/unstructured fixtures
        a = block.find("a", href=True)
        if not a:
            continue
        href = a["href"]
        if href in seen_links:
            continue
        seen_links.add(href)
        page_url = urljoin(base_url, href)
        title = a.get_text(" ", strip=True)
        # find status within the same block (class 'status' common) or nearby
        status_text = ""
        status_el = block.find(class_=re.compile(r"status", re.I))
        if status_el:
            status_text = status_el.get_text(" ", strip=True)
        else:
            # try last td in row
            tds = block.find_all("td")
            if tds:
                status_text = tds[-1].get_text(" ", strip=True)
            else:
                nexts = [s.get_text(" ", strip=True) for s in block.find_all_next(limit=3)]
                status_text = " ".join(nexts)
        status = _normalize_status(status_text)
        if not (status.lower().startswith('published') or 'published' in status.lower()):
            continue
        date_text = None
        date_el = block.find(class_=re.compile(r"date", re.I))
        if date_el:
            date_text = date_el.get_text(" ", strip=True)
        else:
            tds = block.find_all("td")
            if tds:
                date_text = tds[0].get_text(" ", strip=True)
        published_date = _parse_date(date_text) if date_text else None
        if href.lower().endswith('.pdf'):
            continue
        entries.append(TranscriptEntry(title=title, page_url=page_url, pdf_url=None, published_date=published_date, status=status))
    return entries


def _looks_like_aph_404(resp) -> bool:
    # APH sometimes returns a 404 helper page URL like /Help/404?item=...
    url = getattr(resp, "url", "") or ""
    if "/Help/404" in url:
        return True
    status = getattr(resp, "status_code", None)
    return status == 404


DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; estimates-monitor/0.1; +https://github.com/openclaw/openclaw)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def _fetch_schedule(session: Optional[requests.Session] = None, timeout_s: int = 30):
    s = session or requests
    last_exc = None

    # Be resilient to transient APH outages (502/503/504) and slow responses.
    # But also respect the caller's overall timeout budget.
    deadline = time.time() + max(1, timeout_s)

    for url in SCHEDULE_URL_CANDIDATES:
        remaining = max(1, int(deadline - time.time()))
        if remaining <= 0:
            break
        try:
            # Separate connect/read timeouts. Keep connect tight so we fail fast on network issues.
            resp = s.get(url, headers=DEFAULT_HEADERS, timeout=(5, remaining))

            # if requests, resp.url is the final URL after redirects
            if _looks_like_aph_404(resp):
                continue

            status = getattr(resp, "status_code", None)
            if status and status >= 500:
                last_exc = requests.exceptions.HTTPError(f"{status} Server Error for url: {url}", response=resp)
                continue

            resp.raise_for_status()
            return resp
        except Exception as e:
            last_exc = e
            continue

    if last_exc:
        raise last_exc
    raise RuntimeError("Failed to fetch schedule")


def get_schedule(session: Optional[requests.Session] = None, timeout_s: int = 30) -> List[TranscriptEntry]:
    resp = _fetch_schedule(session=session, timeout_s=timeout_s)
    base_url = getattr(resp, "url", None) or SCHEDULE_URL
    return _parse_schedule_html(resp.text, base_url=base_url)


def _sort_key_latest(e: TranscriptEntry):
    # Latest ordering: primarily by Ref No. descending (if present), date as fallback.
    has_ref = 1 if e.ref_no is not None else 0
    ref = e.ref_no or -1
    has_date = 1 if e.published_date is not None else 0
    dt = e.published_date or datetime.min
    return (has_ref, ref, has_date, dt)


def _extract_estimate_id_parts(display_url: str):
    # From display URLs like ...query=Id:"committees/estimate/29366/0002"
    from urllib.parse import unquote
    decoded = unquote(display_url or "")
    m = re.search(r"committees/estimate/(\d+)/(\d+)", decoded)
    if not m:
        return None, None, None
    est, doc = m.group(1), m.group(2)
    return est, doc, f"committees/estimate/{est}/{doc}"


def _pick_pdf_link(html: str, base_url: str, estimate_id: str = None, id_str: str = None):
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href:
            continue
        href_l = href.lower()
        if ".pdf" not in href_l and "application%2fpdf" not in href_l and "application/pdf" not in href_l:
            continue
        if "parlinfo/download" not in href_l and not href_l.endswith(".pdf"):
            # allow generic .pdf links too
            pass
        links.append((a.get_text(" ", strip=True) or "", href))

    if not links:
        return None

    # Filter to matching estimate id if possible
    if estimate_id:
        decoded_links = []
        from urllib.parse import unquote, urlparse
        for txt, href in links:
            decoded_links.append((txt, href, unquote(href)))
        # Prefer explicit ParlInfo download links for this estimate id
        matching = [(txt, href, dec) for (txt, href, dec) in decoded_links if f"parlinfo/download" in dec and f"committees/estimate/{estimate_id}/" in dec]
        if matching:
            # Hard preference: if any toc_pdf links exist, restrict to those
            toc = [(txt, href, dec) for (txt, href, dec) in matching if "/toc_pdf/" in dec]
            if toc:
                matching = toc
            # Prefer ones whose fragment references the exact id_str (e.g. #search=...)
            if id_str:
                exact = []
                for (txt, href, dec) in matching:
                    parsed = urlparse(href)
                    frag = parsed.fragment or ""
                    if id_str in frag or id_str in dec:
                        exact.append((txt, href, dec))
                if exact:
                    matching = exact
            # pick first after filtering
            _, href, dec = matching[0]
            # validate final choice contains committees/estimate/<id>/
            if f"committees/estimate/{estimate_id}/" in dec:
                return urljoin(base_url, href)
            # otherwise fall through to allow other heuristics
        # Additional preference: if any link explicitly contains /toc_pdf/ for this estimate id, pick it
        for txt, href, dec in decoded_links:
            if f"committees/estimate/{estimate_id}/" in dec and "/toc_pdf/" in dec:
                return urljoin(base_url, href)

    # Fallback: first pdf link
    return urljoin(base_url, links[0][1])

    # Fallback: first pdf link
    return urljoin(base_url, links[0][1])


def get_latest_published(session: Optional[requests.Session] = None, is_seen_func=None, timeout_s: int = 30) -> Optional[TranscriptEntry]:
    s = session or requests
    resp = _fetch_schedule(session=session, timeout_s=timeout_s)
    base_url = getattr(resp, "url", None) or SCHEDULE_URL
    entries = _parse_schedule_html(resp.text, base_url=base_url)
    if not entries:
        return None

    # Sort by required ordering
    entries.sort(key=_sort_key_latest, reverse=True)

    chosen = None
    if is_seen_func:
        for e in entries:
            if not is_seen_func(e.page_url):
                chosen = e
                break
    if chosen is None:
        chosen = entries[0]
    # ensure pdf_url resolved: if missing, fetch detail page and look for .pdf link
    if not chosen.pdf_url:
        detail_html = None
        detail_base = chosen.page_url
        try:
            detail_resp = s.get(chosen.page_url, headers=DEFAULT_HEADERS, timeout=timeout_s)
            # Some session implementations (tests) may not raise a requests HTTPError with a response attached
            # so normalise: if status_code==403, raise an HTTPError to trigger fallback behaviour below.
            if getattr(detail_resp, 'status_code', None) == 403:
                raise requests.exceptions.HTTPError(response=detail_resp)
            detail_resp.raise_for_status()
            detail_html = detail_resp.text
            detail_base = getattr(detail_resp, "url", None) or chosen.page_url
        except Exception as e:
            # If we got a 403 from ParlInfo, attempt a browser-based HTML fetcher before falling back to the committee page.
            resp_obj = getattr(e, 'response', None)
            resp_status = getattr(resp_obj, 'status_code', None)
            if resp_status == 403:
                # Try the fetch_html abstraction (which will attempt a browser snapshot if needed)
                try:
                    from estimates_monitor.fetcher import fetch_html
                    fetched = fetch_html(chosen.page_url, session=s if s is not requests else None)
                    detail_html = fetched
                    detail_base = chosen.page_url
                    # We were able to fetch via browser fallback; do not set committee fallback
                except Exception:
                    # If browser fallback also failed, only then try the committee page
                    if chosen.committee_url:
                        fallback_resp = s.get(chosen.committee_url, headers=DEFAULT_HEADERS, timeout=timeout_s)
                        fallback_resp.raise_for_status()
                        detail_html = fallback_resp.text
                        detail_base = getattr(fallback_resp, "url", None) or chosen.committee_url
                        chosen.pdf_fallback_committee = True
                    else:
                        raise
            else:
                # propagate original exception for non-403 errors
                raise

        # If this is a ParlInfo display page, prefer the specialised extractor which knows about toc_pdf/download links
        parsed_page = urlparse(chosen.page_url)
        hostname = (parsed_page.hostname or "").lower()
        # If we fell back to the committee page due to a ParlInfo 403, avoid using the ParlInfo display URL as the base
        # for resolving links — instead prefer the committee response base (detail_base) which will be an aph.gov.au host.
        if "parlinfo.aph.gov.au" in hostname and not chosen.pdf_fallback_committee:
            pdf_from_parlinfo = parlinfo.extract_pdf_url(chosen.page_url, detail_html or "")
            if pdf_from_parlinfo:
                chosen.pdf_url = pdf_from_parlinfo
            else:
                # fall through to generic scanning
                pass

        # Generic HTML scanning/picking as a fallback for non-ParlInfo or when extractor didn't find anything
        est_id, doc_id, id_str = _extract_estimate_id_parts(chosen.page_url)
        pdf = _pick_pdf_link(detail_html, detail_base, estimate_id=est_id, id_str=id_str)
        if pdf and not chosen.pdf_url:
            chosen.pdf_url = pdf

        # Safeguard: if we fell back to the committee page and the resolved pdf_url points at parlinfo.aph.gov.au
        # with a path like '/-/media/...', rewrite the host to 'www.aph.gov.au' to avoid the parlinfo media 403 issue.
        if chosen.pdf_fallback_committee and chosen.pdf_url:
            parsed_pdf = urlparse(chosen.pdf_url)
            # If the path indicates an APH media resource (/ -/media/...), ensure host is the public APH domain.
            # This covers cases where resolution used an unrelated base (e.g. parlinfo or example.org in tests).
            if parsed_pdf.path.startswith("/-/media/"):
                # replace host with www.aph.gov.au and keep rest of URL
                new_pdf = parsed_pdf._replace(scheme="https", netloc="www.aph.gov.au")
                chosen.pdf_url = new_pdf.geturl()
    return chosen

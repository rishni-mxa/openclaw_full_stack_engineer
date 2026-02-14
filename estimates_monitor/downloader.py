import requests
from pathlib import Path
from urllib.parse import urlparse, urlsplit, urlunsplit
import hashlib
import re
import tempfile
from typing import Optional
import subprocess
import sys
import json

PDF_DIR = Path("data/pdfs")
PDF_DIR.mkdir(parents=True, exist_ok=True)


def _slugify(text: str) -> str:
    if not text:
        return "transcript"
    t = text.lower()
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return t or "transcript"


def download_pdf(pdf_url: str, filename_hint: str = None, timeout: int = 30) -> str:
    """Download a PDF via HTTP and return local path."""
    resp = requests.get(pdf_url, stream=True, timeout=timeout)
    resp.raise_for_status()
    if filename_hint:
        safe_name = filename_hint.replace("/", "_")
    else:
        p = urlparse(pdf_url)
        safe_name = Path(p.path).name or "transcript.pdf"
    out = PDF_DIR / safe_name
    with out.open("wb") as f:
        for chunk in resp.iter_content(8192):
            if chunk:
                f.write(chunk)
    return str(out)


def _strip_url_fragment(url: str) -> str:
    """Fragments never reach the server but can break some clients/logging."""
    parts = urlsplit(url)
    if not parts.fragment:
        return url
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))


def _download_pdf_bytes_with_playwright(
    pdf_url: str,
    profile_dir: Path,
    timeout_ms: int = 60000,
    referer_url: Optional[str] = None,
    verbose: bool = False,
) -> bytes:
    """Download bytes using Playwright via a subprocess helper.

    Rationale: Playwright calls can hang in-process; subprocess lets us hard-timeout and kill.
    """
    profile_dir.mkdir(parents=True, exist_ok=True)
    url = _strip_url_fragment(pdf_url)
    referer_url = _strip_url_fragment(referer_url) if referer_url else None

    out_tmp = Path(tempfile.mkstemp(prefix="pwpdf", suffix=".pdf", dir=str(profile_dir.parent))[1])

    cmd = [
        sys.executable,
        "-m",
        "estimates_monitor.pw_download",
        "--url",
        url,
        "--profile",
        str(profile_dir),
        "--out",
        str(out_tmp),
        "--timeout-ms",
        str(timeout_ms),
    ]
    if referer_url:
        cmd += ["--referer", referer_url]
    if verbose:
        cmd += ["--verbose"]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=max(5, int(timeout_ms / 1000) + 10))
    except subprocess.TimeoutExpired as e:
        raise requests.HTTPError(f"Playwright PDF download timed out for {url}") from e

    # Parse last line JSON if present
    stdout = (proc.stdout or "").strip().splitlines()
    last = stdout[-1] if stdout else ""
    try:
        result = json.loads(last) if last else {"ok": False, "error": "no_output"}
    except Exception:
        result = {"ok": False, "error": "bad_output", "detail": last[:200]}

    if not result.get("ok"):
        raise requests.HTTPError(f"Playwright PDF download failed for {url}: {result}")

    data = Path(result["path"]).read_bytes()
    try:
        Path(result["path"]).unlink(missing_ok=True)
    except Exception:
        pass
    return data


def download_pdf_deterministic(
    pdf_url: str,
    base_name: str,
    session=None,
    timeout: int = 30,
    hash_prefix_len: int = 8,
    out_dir: Optional[Path] = None,
    playwright_profile_dir: Optional[Path] = None,
    playwright_referer_url: Optional[str] = None,
    verbose: bool = False,
):
    """Download a PDF deterministically.

    Primary: requests streaming (session or requests).
    Fallback: if HTTP 403, use Playwright persistent context to fetch bytes (WAF).
    """
    out_dir = out_dir or PDF_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    url = _strip_url_fragment(pdf_url)
    s = session or requests

    resp = None
    content_iter = None
    bytes_direct: Optional[bytes] = None

    try:
        resp = s.get(url, stream=True, timeout=timeout)
        resp.raise_for_status()
        content_iter = resp.iter_content(8192)
    except Exception as e:
        # If 403, try Playwright fallback (only if profile dir provided or default).
        status = None
        if hasattr(e, "response") and getattr(e, "response", None) is not None:
            status = getattr(e.response, "status_code", None)
        elif resp is not None:
            status = getattr(resp, "status_code", None)

        if status == 403:
            profile = playwright_profile_dir or Path("data/playwright-profile")
            bytes_direct = _download_pdf_bytes_with_playwright(
                url,
                profile,
                timeout_ms=int(timeout * 1000),
                referer_url=playwright_referer_url,
                verbose=verbose,
            )
        else:
            raise

    hasher = hashlib.sha256()
    total = 0
    tmp_fd, tmp_path = tempfile.mkstemp(prefix="pdf", dir=str(out_dir))

    with open(tmp_fd, "wb") as f:
        if bytes_direct is not None:
            f.write(bytes_direct)
            hasher.update(bytes_direct)
            total = len(bytes_direct)
        else:
            for chunk in content_iter:
                if chunk:
                    f.write(chunk)
                    hasher.update(chunk)
                    total += len(chunk)

    sha = hasher.hexdigest()
    base = _slugify(base_name)
    filename = f"{base}_{sha[:hash_prefix_len]}.pdf"
    final_path = out_dir / filename
    Path(tmp_path).replace(final_path)
    return {"path": str(final_path), "sha256": sha, "bytes": total}

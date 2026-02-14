"""PDF downloader using requests.

Browser-based WAF bypass (for ParlInfo's Azure WAF) is handled by the OpenClaw
agent's browser tool, not this module.  This module provides deterministic
downloads via plain HTTP requests.
"""

import requests
from pathlib import Path
from urllib.parse import urlparse, urlsplit, urlunsplit
import hashlib
import re
import tempfile
from typing import Optional

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


def download_pdf_deterministic(
    pdf_url: str,
    base_name: str,
    session=None,
    timeout: int = 30,
    hash_prefix_len: int = 8,
    out_dir: Optional[Path] = None,
    **kwargs,
):
    """Download a PDF deterministically with content-hash naming.

    Uses requests streaming.  Raises requests.HTTPError on failure (including
    403 WAF blocks — callers that need browser-based bypass should handle this
    at the orchestration layer via the OpenClaw browser tool).
    """
    out_dir = out_dir or PDF_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    url = _strip_url_fragment(pdf_url)
    s = session or requests

    resp = s.get(url, stream=True, timeout=timeout)
    resp.raise_for_status()

    hasher = hashlib.sha256()
    total = 0
    tmp_fd, tmp_path = tempfile.mkstemp(prefix="pdf", dir=str(out_dir))

    with open(tmp_fd, "wb") as f:
        for chunk in resp.iter_content(8192):
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

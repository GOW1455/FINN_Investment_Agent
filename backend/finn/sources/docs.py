"""Download a primary-source PDF once and keep its text page by page."""
import hashlib

import fitz  # PyMuPDF
import httpx

from .. import store
from ..config import DOCS, UA


def pages(url: str, max_pages: int | None = None) -> list[str]:
    """Text of each page (index 0 is page 1). Cached on disk by URL."""
    key = hashlib.sha1(url.encode()).hexdigest()[:16]
    path = DOCS / f"{key}.json"
    cached = store.read(path)
    if cached is not None and (max_pages is None or cached["complete"] or len(cached["pages"]) >= max_pages):
        return cached["pages"][:max_pages] if max_pages else cached["pages"]

    headers = {"User-Agent": UA, "Referer": "https://www.bseindia.com/", "Accept": "application/pdf,*/*"}
    with httpx.Client(headers=headers, timeout=90, follow_redirects=True) as client:
        response = client.get(url)
        response.raise_for_status()
        body = response.content
    if not body.startswith(b"%PDF"):
        raise RuntimeError(f"not a PDF: {url}")
    with fitz.open(stream=body, filetype="pdf") as pdf:
        total = pdf.page_count
        limit = min(total, max_pages) if max_pages else total
        text = [pdf[i].get_text("text") for i in range(limit)]
    store.write(path, {"url": url, "complete": limit == total, "pages": text})
    return text

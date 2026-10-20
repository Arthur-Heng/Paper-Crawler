"""bioRxiv / medRxiv crawler using the official REST API (https://api.biorxiv.org).

Endpoint used: ``/details/{server}/{start}/{end}/{cursor}`` which returns every preprint *version*
posted in the inclusive date window, 30 per page, newest first.  Pagination advances ``cursor`` by
the number of items returned until ``total`` is reached.  Category filtering is done server-side
with ``?category=...`` (spaces become underscores, e.g. ``cell_biology``).

Each item is normalised to a flat dict; by default only the newest version of each DOI is kept.
"""
from __future__ import annotations

import datetime as dt
import logging
import re
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

import requests

from .common import DEFAULT_TIMEOUT, RateLimiter, make_session

log = logging.getLogger("paper_crawler.rxiv")

API_BASE = "https://api.biorxiv.org"
SERVER_SITES = {
    "biorxiv": "https://www.biorxiv.org",
    "medrxiv": "https://www.medrxiv.org",
}

RXIV_CSV_FIELDS = [
    "doi", "version", "date", "title", "category", "type", "license", "authors",
    "author_corresponding", "author_corresponding_institution", "published_doi", "url", "pdf_url",
    "jatsxml", "abstract",
]


def normalize_category(category: Optional[str]) -> Optional[str]:
    if not category:
        return None
    return re.sub(r"\s+", "_", category.strip().lower())


class RxivClient:
    def __init__(self, session: Optional[requests.Session] = None, requests_per_second: float = 2.0):
        self.session = session or make_session()
        self.limiter = RateLimiter(requests_per_second)

    def _get_page(self, server: str, start: dt.date, end: dt.date, cursor: int, category: Optional[str]) -> Dict[str, Any]:
        url = f"{API_BASE}/details/{server}/{start.isoformat()}/{end.isoformat()}/{cursor}"
        params = {"category": category} if category else None
        self.limiter.wait()
        r = self.session.get(url, params=params, timeout=DEFAULT_TIMEOUT)
        r.raise_for_status()
        return r.json()

    def iter_details(self, server: str, start: dt.date, end: dt.date, category: Optional[str] = None) -> Iterator[Dict[str, Any]]:
        """Yield normalised records (all versions) posted on `server` within [start, end]."""
        if server not in SERVER_SITES:
            raise ValueError(f"server must be one of {sorted(SERVER_SITES)}, got {server!r}")
        category = normalize_category(category)
        cursor, total, seen = 0, None, 0
        while True:
            data = self._get_page(server, start, end, cursor, category)
            msg = (data.get("messages") or [{}])[0]
            status = msg.get("status")
            coll = data.get("collection") or []
            if total is None:
                try:
                    total = int(msg.get("total") or 0)
                except (TypeError, ValueError):
                    total = 0
                log.info("%s %s..%s%s: %d version records", server, start, end,
                         f" [{category}]" if category else "", total)
            if status != "ok":
                if status != "no posts found":
                    log.warning("%s API status %r at cursor %d: %s", server, status, cursor, msg)
                break
            if not coll:
                break
            for item in coll:
                if category and normalize_category(item.get("category")) != category:
                    continue  # defensive: server should already have filtered
                yield normalize_item(item, server)
            seen += len(coll)
            cursor += len(coll)
            if total and cursor >= total:
                break
        if total and seen != total:
            log.warning("%s %s..%s: expected %d items, got %d", server, start, end, total, seen)


def normalize_item(item: Dict[str, Any], server: str) -> Dict[str, Any]:
    doi = (item.get("doi") or "").strip()
    try:
        version = int(item.get("version") or 1)
    except (TypeError, ValueError):
        version = 1
    site = SERVER_SITES.get(server, SERVER_SITES["biorxiv"])
    published = (item.get("published") or "").strip()
    authors = [a.strip() for a in (item.get("authors") or "").split(";") if a.strip()]
    return {
        "source": server,
        "doi": doi,
        "version": version,
        "date": item.get("date"),
        "title": " ".join((item.get("title") or "").split()),
        "abstract": (item.get("abstract") or "").strip(),
        "authors": authors,
        "author_corresponding": item.get("author_corresponding"),
        "author_corresponding_institution": item.get("author_corresponding_institution"),
        "category": item.get("category"),
        "type": item.get("type"),
        "license": item.get("license"),
        "published_doi": published if published and published.upper() != "NA" else None,
        "jatsxml": item.get("jatsxml"),
        "url": f"{site}/content/{doi}v{version}" if doi else None,
        "pdf_url": f"{site}/content/{doi}v{version}.full.pdf" if doi else None,
    }


# ---------------------------------------------------------------------------
# Optional full text (JATS XML) download
# ---------------------------------------------------------------------------

def safe_filename(doi: str, version: int) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", f"{doi}v{version}")


def download_jats(session: requests.Session, limiter: RateLimiter, record: Dict[str, Any], out_dir: Path,
                  overwrite: bool = False) -> Optional[Path]:
    """Download the JATS full-text XML linked from the API record. Returns the path, or None on failure.

    Note: biorxiv.org / medrxiv.org sit behind Cloudflare and may answer 403 to automated clients.
    """
    url = record.get("jatsxml")
    if not url:
        return None
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"{safe_filename(record['doi'], record['version'])}.xml"
    if dest.exists() and not overwrite:
        return dest
    limiter.wait()
    try:
        r = session.get(url, timeout=120)
        if r.status_code != 200 or b"<article" not in r.content[:5000]:
            hint = " - site is rate-limiting automated clients" if r.status_code in (403, 429) else ""
            log.warning("JATS download failed for %s (HTTP %s%s)", record.get("doi"), r.status_code, hint)
            return None
        dest.write_bytes(r.content)
        return dest
    except requests.RequestException as e:
        log.warning("JATS download error for %s: %s", record.get("doi"), e)
        return None

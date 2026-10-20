"""Shared helpers: HTTP session with retries, rate limiting, date chunking, JSONL/CSV output."""
from __future__ import annotations

import csv
import datetime as dt
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger("paper_crawler")

DEFAULT_TIMEOUT = 60


class RateLimiter:
    """Simple blocking rate limiter: at most `per_second` calls per second."""

    def __init__(self, per_second: float):
        self.min_interval = 1.0 / per_second if per_second and per_second > 0 else 0.0
        self._last = 0.0

    def wait(self) -> None:
        if self.min_interval <= 0:
            return
        now = time.monotonic()
        delta = now - self._last
        if delta < self.min_interval:
            time.sleep(self.min_interval - delta)
        self._last = time.monotonic()


def make_session(user_agent: Optional[str] = None, total_retries: int = 6, backoff: float = 1.0) -> requests.Session:
    """requests.Session with exponential backoff on 429/5xx (honours Retry-After)."""
    retry = Retry(
        total=total_retries,
        connect=total_retries,
        read=total_retries,
        status=total_retries,
        backoff_factor=backoff,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "POST"]),
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    contact = os.getenv("NCBI_EMAIL", "")
    session.headers["User-Agent"] = user_agent or f"paper-crawler/0.1 (python-requests; contact: {contact or 'unset'})"
    return session


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------

def parse_date(s: str) -> dt.date:
    """Accept YYYY-MM-DD or YYYY/MM/DD."""
    return dt.date.fromisoformat(s.replace("/", "-"))


def resolve_date_range(start: Optional[str], end: Optional[str], days: Optional[int]) -> Tuple[dt.date, dt.date]:
    """Resolve --start/--end/--days into a concrete inclusive date range."""
    today = dt.date.today()
    if start and end:
        s, e = parse_date(start), parse_date(end)
    elif start:
        s = parse_date(start)
        e = s + dt.timedelta(days=(days or 30))
        e = min(e, today)
    elif end:
        e = parse_date(end)
        s = e - dt.timedelta(days=(days or 30))
    else:
        e = today
        s = today - dt.timedelta(days=(days or 30))
    if s > e:
        raise ValueError(f"start date {s} is after end date {e}")
    return s, e


def date_chunks(start: dt.date, end: dt.date, chunk_days: int) -> Iterator[Tuple[dt.date, dt.date]]:
    """Yield inclusive (chunk_start, chunk_end) windows of at most `chunk_days` days."""
    chunk_days = max(1, int(chunk_days))
    cur = start
    while cur <= end:
        nxt = min(cur + dt.timedelta(days=chunk_days - 1), end)
        yield cur, nxt
        cur = nxt + dt.timedelta(days=1)


def chunk_name(a: dt.date, b: dt.date) -> str:
    return a.isoformat() if a == b else f"{a.isoformat()}_{b.isoformat()}"


# ---------------------------------------------------------------------------
# JSONL / CSV
# ---------------------------------------------------------------------------

def write_jsonl(path: Path, records: Iterable[Dict[str, Any]]) -> int:
    """Write records to `path` atomically (via a .tmp file). Returns the number written."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    n = 0
    with open(tmp, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False))
            f.write("\n")
            n += 1
    os.replace(tmp, path)
    return n


def read_jsonl(path: Path) -> Iterator[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def _csv_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        parts = []
        for v in value:
            if isinstance(v, dict):
                parts.append(v.get("name") or json.dumps(v, ensure_ascii=False))
            else:
                parts.append(str(v))
        return "; ".join(parts)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value).replace("\r", " ")


def write_csv(path: Path, records: Iterable[Dict[str, Any]], fields: Sequence[str]) -> int:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    n = 0
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(fields)
        for rec in records:
            w.writerow([_csv_cell(rec.get(k)) for k in fields])
            n += 1
    os.replace(tmp, path)
    return n


# ---------------------------------------------------------------------------
# Resumable chunked crawl
# ---------------------------------------------------------------------------

def run_chunked(
    source: str,
    start: dt.date,
    end: dt.date,
    chunk_days: int,
    out_dir: Path,
    fetch_chunk: Callable[[dt.date, dt.date], Iterable[Dict[str, Any]]],
    force: bool = False,
) -> List[Path]:
    """Run `fetch_chunk` for each date window, saving one JSONL per window under out_dir/daily.

    Windows whose JSONL already exists are skipped unless `force` is set, so an interrupted
    crawl can simply be re-run.  Returns the list of chunk files (in date order).
    """
    from tqdm import tqdm  # local import so the module can be used without tqdm

    daily_dir = Path(out_dir) / "daily"
    daily_dir.mkdir(parents=True, exist_ok=True)
    chunks = list(date_chunks(start, end, chunk_days))
    files: List[Path] = []
    skipped = 0
    for a, b in tqdm(chunks, desc=f"{source} {start}..{end}", unit="chunk"):
        path = daily_dir / f"{chunk_name(a, b)}.jsonl"
        files.append(path)
        if path.exists() and not force:
            skipped += 1
            continue
        n = write_jsonl(path, fetch_chunk(a, b))
        log.info("%s %s: %d records -> %s", source, chunk_name(a, b), n, path)
    if skipped:
        log.info("%s: skipped %d existing chunk(s); use --force to re-fetch", source, skipped)
    return files


def merge_chunks(files: Sequence[Path]) -> Iterator[Dict[str, Any]]:
    for p in files:
        if p.exists():
            yield from read_jsonl(p)


def dedupe(records: Iterable[Dict[str, Any]], key: str, version_key: Optional[str] = None) -> List[Dict[str, Any]]:
    """Keep one record per `key`. With `version_key`, keep the highest version; else keep the last seen."""
    best: Dict[Any, Dict[str, Any]] = {}
    order: List[Any] = []
    for rec in records:
        k = rec.get(key)
        if k is None:
            continue
        if k not in best:
            best[k] = rec
            order.append(k)
        elif version_key is None or (rec.get(version_key) or 0) >= (best[k].get(version_key) or 0):
            best[k] = rec
    return [best[k] for k in order]


def write_summary(path: Path, payload: Dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

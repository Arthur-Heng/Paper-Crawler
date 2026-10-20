"""Command-line interface.

    python -m paper_crawler all      --days 30 --out data
    python -m paper_crawler pubmed   --start 2026-09-20 --end 2026-10-20 [--query "..."] [--datetype edat]
    python -m paper_crawler biorxiv  --days 30 [--category neuroscience] [--all-versions] [--fulltext]
    python -m paper_crawler medrxiv  --days 30
    python -m paper_crawler pmc-fulltext --input data/pubmed/pubmed_<start>_<end>.jsonl --out data/pubmed/fulltext
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import __version__
from .common import (RateLimiter, dedupe, make_session, merge_chunks, read_jsonl, resolve_date_range,
                     run_chunked, write_csv, write_jsonl, write_summary)
from .pubmed import PUBMED_CSV_FIELDS, PubMedClient
from .rxiv import RXIV_CSV_FIELDS, RxivClient, download_jats

log = logging.getLogger("paper_crawler")


# ---------------------------------------------------------------------------
# argument groups
# ---------------------------------------------------------------------------

def _add_range_args(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("date range (inclusive)")
    g.add_argument("--start", help="YYYY-MM-DD (default: today minus --days)")
    g.add_argument("--end", help="YYYY-MM-DD (default: today)")
    g.add_argument("--days", type=int, default=30, help="window length when --start/--end are not both given (default 30)")
    g.add_argument("--chunk-days", type=int, default=1, help="days per request window / checkpoint file (default 1)")
    p.add_argument("--out", default="data", help="output root directory (default ./data)")
    p.add_argument("--force", action="store_true", help="re-fetch windows that already have a checkpoint file")
    p.add_argument("--log-level", default="INFO")


def _add_ncbi_args(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("PubMed / NCBI")
    g.add_argument("--email", help="contact email for NCBI (or env NCBI_EMAIL)")
    g.add_argument("--api-key", help="NCBI API key, raises limit from 3 to 10 req/s (or env NCBI_API_KEY)")
    g.add_argument("--query", help="optional PubMed query to AND with the date window, e.g. '\"single cell\"[tiab]'")
    g.add_argument("--datetype", default="edat", choices=["edat", "pdat", "crdt", "mhda"],
                   help="which PubMed date the window applies to (default edat = date added to PubMed)")
    g.add_argument("--batch-size", type=int, default=500, help="records per efetch call (default 500)")
    g.add_argument("--save-xml", action="store_true", help="also keep the raw efetch XML batches")


def _add_rxiv_args(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("bioRxiv / medRxiv")
    g.add_argument("--category", help="subject category filter, e.g. neuroscience, cell_biology")
    g.add_argument("--all-versions", action="store_true", help="keep every posted version instead of only the newest per DOI")
    g.add_argument("--fulltext", action="store_true", help="also download JATS full-text XML (may be blocked by Cloudflare)")
    g.add_argument("--rxiv-rps", type=float, default=2.0, help="requests per second against api.biorxiv.org (default 2)")


# ---------------------------------------------------------------------------
# crawls
# ---------------------------------------------------------------------------

def _export(source: str, out_dir: Path, start: dt.date, end: dt.date, records: List[Dict[str, Any]],
            fields: List[str], extra: Dict[str, Any]) -> Dict[str, Any]:
    stem = f"{source}_{start.isoformat()}_{end.isoformat()}"
    jsonl_path, csv_path, summary_path = out_dir / f"{stem}.jsonl", out_dir / f"{stem}.csv", out_dir / f"{stem}.summary.json"
    write_jsonl(jsonl_path, records)
    write_csv(csv_path, records, fields)
    summary = {
        "source": source, "start": start.isoformat(), "end": end.isoformat(),
        "n_records": len(records), "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "jsonl": str(jsonl_path), "csv": str(csv_path), **extra,
    }
    write_summary(summary_path, summary)
    log.info("%s: %d records -> %s", source, len(records), jsonl_path)
    return summary


def crawl_pubmed(args: argparse.Namespace, start: dt.date, end: dt.date) -> Dict[str, Any]:
    out_dir = Path(args.out) / "pubmed"
    client = PubMedClient(email=args.email, api_key=args.api_key)
    xml_dir = out_dir / "raw_xml" if args.save_xml else None

    def fetch(a: dt.date, b: dt.date):
        return client.iter_records(a, b, query=args.query, datetype=args.datetype,
                                   batch_size=args.batch_size, save_xml_dir=xml_dir)

    files = run_chunked("pubmed", start, end, args.chunk_days, out_dir, fetch, force=args.force)
    per_day = {f.stem: sum(1 for _ in read_jsonl(f)) for f in files if f.exists()}
    records = dedupe(merge_chunks(files), key="pmid")
    extra = {"datetype": args.datetype, "query": args.query or "all[sb]", "per_window": per_day,
             "n_with_pmcid": sum(1 for r in records if r.get("pmcid")),
             "n_with_abstract": sum(1 for r in records if r.get("abstract"))}
    return _export("pubmed", out_dir, start, end, records, PUBMED_CSV_FIELDS, extra)


def crawl_rxiv(server: str, args: argparse.Namespace, start: dt.date, end: dt.date) -> Dict[str, Any]:
    out_dir = Path(args.out) / server
    client = RxivClient(requests_per_second=args.rxiv_rps)

    def fetch(a: dt.date, b: dt.date):
        return client.iter_details(server, a, b, category=args.category)

    files = run_chunked(server, start, end, args.chunk_days, out_dir, fetch, force=args.force)
    per_day = {f.stem: sum(1 for _ in read_jsonl(f)) for f in files if f.exists()}
    all_versions = list(merge_chunks(files))
    records = all_versions if args.all_versions else dedupe(all_versions, key="doi", version_key="version")
    extra = {"category": args.category, "all_versions": bool(args.all_versions),
             "n_version_records": len(all_versions), "per_window": per_day,
             "n_new_results": sum(1 for r in records if (r.get("type") or "").lower() == "new results")}
    if args.fulltext:
        ft_dir = out_dir / "fulltext_jats"
        session, limiter = make_session(total_retries=0), RateLimiter(1.0)  # fail fast on 429/403
        ok, consecutive_failures, max_consecutive = 0, 0, 5
        from tqdm import tqdm
        for rec in tqdm(records, desc=f"{server} full text", unit="paper"):
            if download_jats(session, limiter, rec, ft_dir):
                ok += 1
                consecutive_failures = 0
            else:
                consecutive_failures += 1
                if consecutive_failures >= max_consecutive:
                    log.error("%d consecutive JATS download failures; %s.org is probably rate-limiting "
                              "(HTTP 429/403) automated clients. Stopping full-text download. See README "
                              "for the bioRxiv TDM S3 bucket / Europe PMC alternatives.", max_consecutive, server)
                    break
        extra["fulltext_downloaded"] = ok
        extra["fulltext_dir"] = str(ft_dir)
    return _export(server, out_dir, start, end, records, RXIV_CSV_FIELDS, extra)


# ---------------------------------------------------------------------------
# sub-commands
# ---------------------------------------------------------------------------

def cmd_pubmed(args: argparse.Namespace) -> int:
    start, end = resolve_date_range(args.start, args.end, args.days)
    crawl_pubmed(args, start, end)
    return 0


def cmd_rxiv(server: str):
    def _run(args: argparse.Namespace) -> int:
        start, end = resolve_date_range(args.start, args.end, args.days)
        crawl_rxiv(server, args, start, end)
        return 0
    return _run


def cmd_all(args: argparse.Namespace) -> int:
    start, end = resolve_date_range(args.start, args.end, args.days)
    summaries: Dict[str, Any] = {}
    failures: Dict[str, str] = {}
    jobs = [("pubmed", lambda: crawl_pubmed(args, start, end)),
            ("biorxiv", lambda: crawl_rxiv("biorxiv", args, start, end)),
            ("medrxiv", lambda: crawl_rxiv("medrxiv", args, start, end))]
    if args.sources:
        jobs = [j for j in jobs if j[0] in args.sources]
    for name, job in jobs:
        try:
            summaries[name] = job()
        except KeyboardInterrupt:
            raise
        except Exception as e:  # noqa: BLE001 - keep going with the other sources
            log.exception("%s crawl failed: %s", name, e)
            failures[name] = repr(e)
    payload = {"start": start.isoformat(), "end": end.isoformat(),
               "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
               "sources": summaries, "failures": failures}
    path = Path(args.out) / f"summary_{start.isoformat()}_{end.isoformat()}.json"
    write_summary(path, payload)
    print("\n=== paper-crawler summary ===")
    for name, s in summaries.items():
        print(f"  {name:8s} {s['n_records']:7d} records   {s['jsonl']}")
    for name, err in failures.items():
        print(f"  {name:8s} FAILED: {err}")
    print(f"  summary -> {path}")
    return 1 if failures else 0


def cmd_pmc_fulltext(args: argparse.Namespace) -> int:
    from .pmc import download_pmc_fulltext

    client = PubMedClient(email=args.email, api_key=args.api_key)
    records = list(read_jsonl(Path(args.input)))
    stats = download_pmc_fulltext(client, records, Path(args.out), overwrite=args.overwrite,
                                  limit=args.limit, save_txt=not args.no_txt)
    print(stats)
    return 0


# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="paper-crawler",
                                description="Collect recent papers from PubMed, bioRxiv and medRxiv.")
    p.add_argument("--version", action="version", version=f"paper-crawler {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("all", help="crawl PubMed + bioRxiv + medRxiv for the same window")
    _add_range_args(sp); _add_ncbi_args(sp); _add_rxiv_args(sp)
    sp.add_argument("--sources", nargs="+", choices=["pubmed", "biorxiv", "medrxiv"], help="subset of sources to run")
    sp.set_defaults(func=cmd_all)

    sp = sub.add_parser("pubmed", help="crawl PubMed")
    _add_range_args(sp); _add_ncbi_args(sp)
    sp.set_defaults(func=cmd_pubmed)

    for server in ("biorxiv", "medrxiv"):
        sp = sub.add_parser(server, help=f"crawl {server}")
        _add_range_args(sp); _add_rxiv_args(sp)
        sp.set_defaults(func=cmd_rxiv(server))

    sp = sub.add_parser("pmc-fulltext", help="download open-access full text from PMC for a PubMed JSONL")
    sp.add_argument("--input", required=True, help="PubMed JSONL produced by the pubmed/all command")
    sp.add_argument("--out", required=True, help="output directory (xml/ and txt/ are created inside)")
    sp.add_argument("--limit", type=int, help="only process the first N records with a PMCID")
    sp.add_argument("--overwrite", action="store_true")
    sp.add_argument("--no-txt", action="store_true", help="do not write extracted plain-text files")
    sp.add_argument("--email"); sp.add_argument("--api-key")
    sp.add_argument("--log-level", default="INFO")
    sp.set_defaults(func=cmd_pmc_fulltext)
    return p


def main(argv: Optional[List[str]] = None) -> None:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=getattr(logging, str(args.log_level).upper(), logging.INFO),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%H:%M:%S")
    try:
        sys.exit(args.func(args))
    except KeyboardInterrupt:
        log.warning("interrupted; partial windows were not saved, re-run the same command to resume")
        sys.exit(130)


if __name__ == "__main__":
    main()

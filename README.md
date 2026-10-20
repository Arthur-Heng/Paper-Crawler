# paper-crawler

Collect every paper that appeared in **PubMed**, **bioRxiv** and **medRxiv** over a date window
(default: the past 30 days). Output is metadata + abstracts as JSONL and CSV, with optional
full text from PubMed Central.

Only the official, free APIs are used:

| Source | API | What you get | Rate limit used |
|--------|-----|--------------|-----------------|
| PubMed | NCBI E-utilities (`esearch` history server + batched `efetch`) | PMID, DOI, PMCID, title, abstract, journal, dates, authors + affiliations + ORCID, MeSH, keywords, publication types | 3 req/s (10 with a free NCBI API key) |
| bioRxiv | `https://api.biorxiv.org/details/biorxiv/...` | DOI, version, date, title, abstract, authors, corresponding author + institution, category, license, published-journal DOI, JATS/PDF URLs | 2 req/s |
| medRxiv | `https://api.biorxiv.org/details/medrxiv/...` | same as bioRxiv | 2 req/s |

## Quick start

```bash
git clone <this repo> paper-crawler && cd paper-crawler
python -m venv .venv && . .venv/bin/activate      # or: uv venv .venv && . .venv/bin/activate
pip install -e .                                  # installs the `paper-crawler` command

cp .env.example .env                              # put your email (and optional NCBI API key) in it
export NCBI_EMAIL=you@illinois.edu                # or: set -a; . ./.env; set +a

# everything from the last 30 days, all three sources -> ./data
paper-crawler all --days 30 --out data
# equivalently: scripts/collect_last_month.sh
```

Expected size for one month (as of Oct 2026): PubMed ~100-150k records (~1-1.5 GB JSONL,
25-40 min without an API key, 3x faster with one), bioRxiv ~6-8k, medRxiv ~1-2k (a minute or two).

## Commands

```bash
paper-crawler all      --days 30 --out data [--sources pubmed biorxiv] [--query ...] [--category ...]
paper-crawler pubmed   --start 2026-09-20 --end 2026-10-20 [--query '"single cell"[tiab]'] [--datetype edat]
paper-crawler biorxiv  --days 30 [--category neuroscience] [--all-versions] [--fulltext]
paper-crawler medrxiv  --days 30 [--category "infectious diseases"]
paper-crawler pmc-fulltext --input data/pubmed/pubmed_<start>_<end>.jsonl --out data/pubmed/fulltext [--limit 100]
paper-crawler <cmd> --help
```

`python -m paper_crawler ...` works too. Dates are inclusive, `YYYY-MM-DD`.

### Useful options

| Option | Meaning |
|--------|---------|
| `--start/--end/--days` | Window. With neither `--start` nor `--end`, the window is `[today - days, today]`. |
| `--chunk-days N` | The window is crawled in N-day pieces, each saved as its own checkpoint file (default 1). |
| `--force` | Re-fetch pieces that already have a checkpoint file (otherwise they are skipped = resume). |
| `--query` (PubMed) | Any PubMed query, ANDed with the date window. Default `all[sb]` = everything. |
| `--datetype` (PubMed) | Which date the window filters on. `edat` (default) = date the record entered PubMed, i.e. "new in PubMed". `pdat` = journal publication date. |
| `--category` (rxiv) | Server-side subject filter, e.g. `neuroscience`, `cell_biology`, `"infectious diseases"`. |
| `--all-versions` (rxiv) | Keep every version posted in the window. Default keeps only the newest version per DOI. |
| `--fulltext` (rxiv) | Try to download JATS XML full text. See caveat below. |
| `--email/--api-key` | NCBI identification; also read from `NCBI_EMAIL` / `NCBI_API_KEY`. |

## Output layout

```
data/
  summary_<start>_<end>.json              # counts per source, failures, file paths
  pubmed/
    daily/2026-09-20.jsonl ...            # one checkpoint per window piece (resume unit)
    pubmed_<start>_<end>.jsonl            # merged, de-duplicated by PMID
    pubmed_<start>_<end>.csv              # flat subset of fields (lists joined with "; ")
    pubmed_<start>_<end>.summary.json
    fulltext/{xml,txt}/PMC*.xml|txt       # only after `pmc-fulltext`
  biorxiv/  medrxiv/                      # same structure; merged file is newest-version-per-DOI
```

### PubMed record (JSONL)

```json
{"source": "pubmed", "record_type": "article", "pmid": "42891567", "doi": "10.1002/jmv.71182",
 "pmcid": "PMC13675932", "title": "...", "abstract": "BACKGROUND: ...\nMETHODS: ...",
 "journal": "Journal of medical virology", "journal_iso": "J Med Virol", "issn": "1096-9071",
 "volume": "98", "issue": "10", "pages": "e71182", "pub_date": "2026-10", "epub_date": null,
 "entrez_date": "2026-10-17", "pubmed_dates": {"received": "2026-04-06", "accepted": "2026-10-11", "entrez": "2026-10-17", ...},
 "authors": [{"name": "Fabian Ritter", "affiliations": ["..."], "orcid": "0000-0003-4565-5740"}],
 "language": "eng", "publication_types": ["Journal Article"], "mesh_terms": [...], "mesh_major": [...],
 "keywords": [...], "citation_status": "MEDLINE", "url": "https://pubmed.ncbi.nlm.nih.gov/42891567/",
 "pmc_url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC13675932/"}
```

Records from NCBI Bookshelf appear with `"record_type": "book"` and fewer fields.

### bioRxiv / medRxiv record (JSONL)

```json
{"source": "biorxiv", "doi": "10.1101/2025.09.19.677455", "version": 3, "date": "2026-10-17",
 "title": "...", "abstract": "...", "authors": ["Shinozuka, K.", "Yang, W. F. Z."],
 "author_corresponding": "Matthew D Sacchet", "author_corresponding_institution": "Harvard Medical School",
 "category": "neuroscience", "type": "new results", "license": "cc_by_nc", "published_doi": null,
 "jatsxml": "https://www.biorxiv.org/content/early/2026/10/17/2025.09.19.677455.source.xml",
 "url": "https://www.biorxiv.org/content/10.1101/2025.09.19.677455v3",
 "pdf_url": "https://www.biorxiv.org/content/10.1101/2025.09.19.677455v3.full.pdf"}
```

`published_doi` is set when the preprint has since appeared in a journal. `type` is
`new results` / `confirmatory results` / `contradictory results` on bioRxiv and
`PUBLISHAHEADOFPRINT` on medRxiv.

## Full text

* **PubMed -> PMC.** `paper-crawler pmc-fulltext` fetches JATS XML from PubMed Central for every
  record that has a `pmcid` and keeps the ones whose XML actually contains a body (open-access
  articles; roughly a third of PMC records). It also writes a plain-text rendering under `txt/`.
  Non-OA PMCIDs are listed in `no_fulltext.txt` so re-runs skip them.
* **bioRxiv / medRxiv.** The API gives a JATS XML URL per version, but `www.biorxiv.org` /
  `www.medrxiv.org` sit behind Cloudflare and answer **HTTP 429** to scripted downloads of XML and
  PDFs (tested from this cluster, any user agent). `--fulltext` is therefore best effort and stops
  after 5 consecutive failures. For bulk full text use the official routes instead:
  the requester-pays S3 buckets `s3://biorxiv-src-monthly` / `s3://medrxiv-src-monthly`
  (see https://www.biorxiv.org/tdm). Europe PMC also indexes these preprints (source `PPR`) and
  serves full text for a subset of CC-licensed ones via its REST API.

## How it works / caveats

* **PubMed.** For each window piece an `esearch` with `usehistory=y` returns the hit count and a
  `WebEnv`; `efetch` then streams the XML in batches of `--batch-size` (500) via POST, which avoids
  the 10,000-record cap of plain `esearch` paging. XML is parsed with the standard library; use
  `--save-xml` to keep the raw batches. The default 1-day pieces give ~2-8k records each.
* **"Past month" on PubMed.** `edat` is the date NCBI *added* the record, which is what you want
  for a monthly sweep. Note that this includes old papers that were newly indexed. Use
  `--datetype pdat` if you want papers *published* in the window instead.
* **bioRxiv/medRxiv API** returns 30 items per page, newest first, and lists each *version*
  posted in the window; the merged file keeps the newest version per DOI unless `--all-versions`.
  Category filtering is server-side (`?category=`), with a client-side re-check.
* **Resume.** Every window piece is written atomically; re-running the same command skips pieces
  that already exist. To refresh the most recent days (PubMed keeps adding records for a day
  for a while), re-run with `--force` on just those days.
* **Politeness.** Requests are rate-limited and retried with exponential backoff on 429/5xx
  (`Retry-After` is honoured). Please set `NCBI_EMAIL`; NCBI asks for it and may block anonymous
  heavy users.
* Dependencies: Python >= 3.9, `requests`, `tqdm`. No Biopython required.

## Repository layout

```
paper_crawler/
  cli.py      command-line entry point (all / pubmed / biorxiv / medrxiv / pmc-fulltext)
  common.py   HTTP session with retries, rate limiter, date chunking, JSONL/CSV writers, resume logic
  pubmed.py   NCBI E-utilities client + PubMed XML parser
  rxiv.py     bioRxiv / medRxiv API client + record normalisation + JATS download
  pmc.py      PMC open-access full text (XML + plain text)
scripts/
  collect_last_month.sh   `paper-crawler all --days 30 --out data`
  smoke_test.sh           one day from each source into a temp dir
legacy/     the earlier lab scripts this package was distilled from (see legacy/README.md)
```

## Programmatic use

```python
import datetime as dt
from paper_crawler.pubmed import PubMedClient
from paper_crawler.rxiv import RxivClient

pm = PubMedClient(email="you@illinois.edu")
for rec in pm.iter_records(dt.date(2026, 10, 1), dt.date(2026, 10, 7), query='"CRISPR"[tiab]'):
    print(rec["pmid"], rec["title"])

rx = RxivClient()
for rec in rx.iter_details("medrxiv", dt.date(2026, 10, 1), dt.date(2026, 10, 7)):
    print(rec["doi"], rec["version"], rec["title"])
```

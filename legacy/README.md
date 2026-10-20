# Legacy scripts (provenance)

Verbatim copies of the earlier lab crawler code that the new `paper_crawler` package was
distilled from. They are kept for reference only; nothing in `paper_crawler/` imports them.

| File | Original location | What it does |
|------|-------------------|--------------|
| `biochem_paper_crawl/fetch_full_paper.py` | `chem/Biochem_paper_crawl/utils/` | PMC keyword search (esearch) + full-text XML (efetch) + title/abstract/body extraction |
| `biochem_paper_crawl/fetch_pmcid.py` | `chem/Biochem_paper_crawl/pubmed/` | Drug-name -> PMCID search with chemistry/clinical keyword filters (FDA drug pipeline) |
| `biochem_paper_crawl/fetch_xml.py` | `chem/Biochem_paper_crawl/pubmed/` | Batch download of PMC XML for the PMCID lists above |
| `biochem_paper_crawl/extract_text.py`, `fix_formatting_v2.py` | `chem/Biochem_paper_crawl/pubmed/` | PMC XML -> cleaned plain text |
| `biochem_paper_crawl/run_full_collection.sh` | `chem/Biochem_paper_crawl/pubmed/` | The three steps above as one pipeline |
| `opv_crawl/pubmed_utils.py` | `chem/opv/crawl/utils/` | Cleaner PMC search/fetch helpers with retries and metadata extraction (authors, journal, DOI) |
| `opv_crawl/semantic_scholar_utils.py` | `chem/opv/crawl/utils/` | Semantic Scholar search / paper-details helpers |
| `opv_crawl/crawl_paper.py` | `chem/opv/crawl/` | Semantic Scholar + PubMed keyword miner for OPV photostability papers |
| `hypo/semantic_api.py` | `hypo/utils/` | Semantic Scholar client with 429/5xx backoff, citations and references |

Notes
* These scripts hard-code `Entrez.email = "heng6@illinois.edu"` and read the NCBI key from the
  `entrez_api_key` environment variable; the new package uses `NCBI_EMAIL` / `NCBI_API_KEY`.
* They depend on `biopython` (`Bio.Entrez`); the new package only needs `requests` and `tqdm`.
* None of the old code covered bioRxiv or medRxiv; `paper_crawler/rxiv.py` is new.

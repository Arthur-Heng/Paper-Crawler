"""PubMed crawler built on NCBI E-utilities (esearch with the history server + batched efetch).

Date semantics (``datetype``):
  * ``edat`` (default) - Entrez date: the day the record was added to PubMed.  Best match for
    "everything that appeared in PubMed in the past month".
  * ``pdat`` - publication date as printed in the journal issue.
  * ``crdt`` - create date; ``mhda`` - MeSH date.

Rate limits: NCBI allows 3 requests/s without an API key and 10/s with one.  Set
``NCBI_EMAIL`` and (optionally) ``NCBI_API_KEY`` in the environment or pass them explicitly.
"""
from __future__ import annotations

import datetime as dt
import logging
import os
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

import requests

from .common import DEFAULT_TIMEOUT, RateLimiter, make_session

log = logging.getLogger("paper_crawler.pubmed")

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
ESEARCH_RETSTART_LIMIT = 10_000  # documented cap for esearch; efetch via history goes beyond it

PUBMED_CSV_FIELDS = [
    "pmid", "doi", "pmcid", "title", "journal", "journal_iso", "pub_date", "epub_date",
    "entrez_date", "authors", "language", "publication_types", "mesh_terms", "keywords",
    "url", "abstract",
]


class PubMedClient:
    def __init__(
        self,
        email: Optional[str] = None,
        api_key: Optional[str] = None,
        tool: str = "paper-crawler",
        session: Optional[requests.Session] = None,
        requests_per_second: Optional[float] = None,
    ):
        self.email = email or os.getenv("NCBI_EMAIL")
        self.api_key = api_key or os.getenv("NCBI_API_KEY")
        self.tool = tool
        if not self.email:
            log.warning("No NCBI contact email set (NCBI_EMAIL / --email). NCBI asks for one; "
                        "requests will still work but may be throttled or blocked if abusive.")
        rps = requests_per_second or (10.0 if self.api_key else 3.0)
        self.limiter = RateLimiter(rps * 0.9)  # stay a little under the published limit
        self.session = session or make_session()

    # ------------------------------------------------------------------ low level
    def _params(self, **kw: Any) -> Dict[str, Any]:
        p: Dict[str, Any] = {"tool": self.tool}
        if self.email:
            p["email"] = self.email
        if self.api_key:
            p["api_key"] = self.api_key
        p.update(kw)
        return p

    def esearch_history(self, term: str, mindate: dt.date, maxdate: dt.date, datetype: str = "edat"):
        """Run esearch with usehistory=y. Returns (count, webenv, query_key)."""
        params = self._params(
            db="pubmed", term=term, datetype=datetype,
            mindate=mindate.strftime("%Y/%m/%d"), maxdate=maxdate.strftime("%Y/%m/%d"),
            usehistory="y", retmax=0, retmode="json",
        )
        self.limiter.wait()
        r = self.session.get(f"{EUTILS}/esearch.fcgi", params=params, timeout=DEFAULT_TIMEOUT)
        r.raise_for_status()
        data = r.json()
        if "error" in data:
            raise RuntimeError(f"esearch error: {data['error']}")
        res = data["esearchresult"]
        if "ERROR" in res:
            raise RuntimeError(f"esearch error: {res['ERROR']}")
        count = int(res.get("count", 0))
        return count, res.get("webenv"), res.get("querykey")

    def efetch_xml(self, webenv: str, query_key: str, retstart: int, retmax: int) -> bytes:
        data = self._params(db="pubmed", query_key=query_key, WebEnv=webenv,
                            retstart=retstart, retmax=retmax, retmode="xml")
        self.limiter.wait()
        r = self.session.post(f"{EUTILS}/efetch.fcgi", data=data, timeout=300)
        r.raise_for_status()
        return r.content

    def efetch_pmc_xml(self, pmcid: str) -> bytes:
        """Full-text JATS XML for one PMC article (body is present only for open-access articles)."""
        pmcid = pmcid.strip()
        pmcid = pmcid[3:] if pmcid.upper().startswith("PMC") else pmcid
        data = self._params(db="pmc", id=pmcid, rettype="full", retmode="xml")
        self.limiter.wait()
        r = self.session.post(f"{EUTILS}/efetch.fcgi", data=data, timeout=120)
        r.raise_for_status()
        return r.content

    # ------------------------------------------------------------------ high level
    def iter_records(
        self,
        start: dt.date,
        end: dt.date,
        query: Optional[str] = None,
        datetype: str = "edat",
        batch_size: int = 500,
        save_xml_dir: Optional[Path] = None,
    ) -> Iterator[Dict[str, Any]]:
        """Yield parsed PubMed records whose `datetype` falls within [start, end] (inclusive)."""
        term = query.strip() if query and query.strip() else "all[sb]"
        count, webenv, qk = self.esearch_history(term, start, end, datetype)
        log.info("PubMed %s..%s (%s) term=%r: %d records", start, end, datetype, term, count)
        if count == 0:
            return
        if count > ESEARCH_RETSTART_LIMIT:
            log.warning("Window %s..%s has %d records (>%d). Retrieval goes through the history server "
                        "so this should still work; verify the final count or use a smaller --chunk-days.",
                        start, end, count, ESEARCH_RETSTART_LIMIT)
        for retstart in range(0, count, batch_size):
            xml_bytes = self._fetch_batch_with_retry(webenv, qk, retstart, batch_size)
            if save_xml_dir is not None:
                save_xml_dir.mkdir(parents=True, exist_ok=True)
                name = f"{start.isoformat()}_{end.isoformat()}_{retstart:07d}.xml"
                (save_xml_dir / name).write_bytes(xml_bytes)
            for rec in parse_pubmed_xml(xml_bytes):
                yield rec

    def _fetch_batch_with_retry(self, webenv: str, qk: str, retstart: int, retmax: int, attempts: int = 4) -> bytes:
        last_err: Optional[Exception] = None
        for i in range(attempts):
            try:
                xml_bytes = self.efetch_xml(webenv, qk, retstart, retmax)
                _check_efetch_payload(xml_bytes)
                return xml_bytes
            except Exception as e:  # noqa: BLE001 - network / parse errors are retried
                last_err = e
                wait = 2 ** i
                log.warning("efetch retstart=%d failed (%s); retry %d/%d in %ds", retstart, e, i + 1, attempts, wait)
                time.sleep(wait)
        raise RuntimeError(f"efetch failed after {attempts} attempts at retstart={retstart}: {last_err}")


def _check_efetch_payload(xml_bytes: bytes) -> None:
    head = xml_bytes[:400]
    if b"<PubmedArticleSet" not in head and b"<pmc-articleset" not in head:
        snippet = head.decode("utf-8", "replace").strip().replace("\n", " ")
        raise ValueError(f"unexpected efetch payload: {snippet[:200]}")


# ---------------------------------------------------------------------------
# XML parsing
# ---------------------------------------------------------------------------

def _text(el: Optional[ET.Element]) -> str:
    if el is None:
        return ""
    return " ".join("".join(el.itertext()).split())


def _ymd(el: Optional[ET.Element]) -> Optional[str]:
    """Format a <PubDate>/<ArticleDate>/<PubMedPubDate> element as YYYY-MM-DD (or as much as given)."""
    if el is None:
        return None
    y, m, d = _text(el.find("Year")), _text(el.find("Month")), _text(el.find("Day"))
    if not y:
        md = _text(el.find("MedlineDate"))
        return md or None
    months = {"jan": "01", "feb": "02", "mar": "03", "apr": "04", "may": "05", "jun": "06",
              "jul": "07", "aug": "08", "sep": "09", "oct": "10", "nov": "11", "dec": "12"}
    if m and not m.isdigit():
        m = months.get(m[:3].lower(), m)
    out = y
    if m:
        out += f"-{int(m):02d}" if m.isdigit() else f"-{m}"
        if d and d.isdigit():
            out += f"-{int(d):02d}"
    return out


def _parse_article(art: ET.Element) -> Dict[str, Any]:
    mc = art.find("MedlineCitation")
    article = mc.find("Article") if mc is not None else None
    if mc is None or article is None:
        return {}
    pmid = _text(mc.find("PMID"))

    abstract_parts: List[str] = []
    for at in article.findall("Abstract/AbstractText"):
        label = at.get("Label")
        txt = _text(at)
        if txt:
            abstract_parts.append(f"{label}: {txt}" if label else txt)

    journal = article.find("Journal")
    issue = journal.find("JournalIssue") if journal is not None else None

    authors: List[Dict[str, Any]] = []
    for a in article.findall("AuthorList/Author"):
        last, fore = _text(a.find("LastName")), _text(a.find("ForeName"))
        name = f"{fore} {last}".strip() or _text(a.find("CollectiveName"))
        orcid = None
        for ident in a.findall("Identifier"):
            if ident.get("Source") == "ORCID":
                orcid = _text(ident)
        authors.append({
            "name": name,
            "affiliations": [_text(x) for x in a.findall("AffiliationInfo/Affiliation")],
            "orcid": orcid,
        })

    mesh_terms, mesh_major = [], []
    for mh in mc.findall("MeshHeadingList/MeshHeading"):
        desc = mh.find("DescriptorName")
        if desc is None:
            continue
        term = _text(desc)
        mesh_terms.append(term)
        if desc.get("MajorTopicYN") == "Y" or any(q.get("MajorTopicYN") == "Y" for q in mh.findall("QualifierName")):
            mesh_major.append(term)

    ids: Dict[str, str] = {}
    for aid in art.findall("PubmedData/ArticleIdList/ArticleId"):
        t = aid.get("IdType")
        if t and t not in ids:
            ids[t] = _text(aid)
    doi = ids.get("doi")
    if not doi:
        for el in article.findall("ELocationID"):
            if el.get("EIdType") == "doi":
                doi = _text(el)
    pmcid = ids.get("pmc")

    history = {pd.get("PubStatus"): _ymd(pd) for pd in art.findall("PubmedData/History/PubMedPubDate")}

    return {
        "source": "pubmed",
        "record_type": "article",
        "pmid": pmid,
        "doi": doi or None,
        "pmcid": pmcid,
        "title": _text(article.find("ArticleTitle")),
        "abstract": "\n".join(abstract_parts),
        "journal": _text(journal.find("Title")) if journal is not None else "",
        "journal_iso": _text(journal.find("ISOAbbreviation")) if journal is not None else "",
        "issn": _text(journal.find("ISSN")) if journal is not None else "",
        "volume": _text(issue.find("Volume")) if issue is not None else "",
        "issue": _text(issue.find("Issue")) if issue is not None else "",
        "pages": _text(article.find("Pagination/MedlinePgn")),
        "pub_date": _ymd(issue.find("PubDate")) if issue is not None else None,
        "epub_date": _ymd(article.find("ArticleDate")),
        "entrez_date": history.get("entrez"),
        "pubmed_dates": history,
        "authors": authors,
        "language": _text(article.find("Language")),
        "publication_types": [_text(p) for p in article.findall("PublicationTypeList/PublicationType")],
        "mesh_terms": mesh_terms,
        "mesh_major": mesh_major,
        "keywords": [_text(k) for k in mc.findall("KeywordList/Keyword")],
        "citation_status": mc.get("Status"),
        "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        "pmc_url": f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/" if pmcid else None,
    }


def _parse_book(art: ET.Element) -> Dict[str, Any]:
    bd = art.find("BookDocument")
    if bd is None:
        return {}
    pmid = _text(bd.find("PMID"))
    abstract = "\n".join(_text(x) for x in bd.findall("Abstract/AbstractText") if _text(x))
    ids = {a.get("IdType"): _text(a) for a in art.findall("PubmedData/ArticleIdList/ArticleId")}
    history = {pd.get("PubStatus"): _ymd(pd) for pd in art.findall("PubmedData/History/PubMedPubDate")}
    return {
        "source": "pubmed",
        "record_type": "book",
        "pmid": pmid,
        "doi": ids.get("doi"),
        "pmcid": ids.get("pmc"),
        "title": _text(bd.find("ArticleTitle")) or _text(bd.find("Book/BookTitle")),
        "abstract": abstract,
        "journal": _text(bd.find("Book/BookTitle")),
        "pub_date": _ymd(bd.find("Book/PubDate")),
        "entrez_date": history.get("entrez"),
        "pubmed_dates": history,
        "authors": [{"name": f"{_text(a.find('ForeName'))} {_text(a.find('LastName'))}".strip(), "affiliations": [], "orcid": None}
                    for a in bd.findall("AuthorList/Author")],
        "language": _text(bd.find("Language")),
        "publication_types": [_text(p) for p in bd.findall("PublicationType")],
        "mesh_terms": [], "mesh_major": [],
        "keywords": [_text(k) for k in bd.findall("KeywordList/Keyword")],
        "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
    }


def parse_pubmed_xml(xml_bytes: bytes) -> List[Dict[str, Any]]:
    """Parse an efetch PubmedArticleSet into a list of flat dict records."""
    root = ET.fromstring(xml_bytes)
    out: List[Dict[str, Any]] = []
    for child in root:
        if child.tag == "PubmedArticle":
            rec = _parse_article(child)
        elif child.tag == "PubmedBookArticle":
            rec = _parse_book(child)
        else:
            continue
        if rec:
            out.append(rec)
    return out

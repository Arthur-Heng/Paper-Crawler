"""Optional full-text download from PubMed Central for PubMed records that carry a PMCID.

Adapted from the lab's earlier scripts (legacy/biochem_paper_crawl/fetch_full_paper.py and
legacy/opv_crawl/pubmed_utils.py).  efetch on db=pmc returns JATS XML; the <body> is only present
for open-access articles, so non-OA articles are recorded in ``no_fulltext.txt`` instead of saved.
"""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .pubmed import PubMedClient

log = logging.getLogger("paper_crawler.pmc")


def _text(el: Optional[ET.Element]) -> str:
    return " ".join("".join(el.itertext()).split()) if el is not None else ""


def has_body(xml_bytes: bytes, min_chars: int = 200) -> bool:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return False
    body = root.find(".//body")
    return body is not None and len("".join(body.itertext()).strip()) >= min_chars


def extract_sections(xml_bytes: bytes) -> Dict[str, Any]:
    """Return title, abstract and body paragraphs (grouped by top-level section) from PMC JATS XML."""
    root = ET.fromstring(xml_bytes)
    out: Dict[str, Any] = {"title": _text(root.find(".//article-title")), "abstract": "", "sections": []}
    abstract = root.find(".//abstract")
    if abstract is not None:
        paras = [_text(p) for p in abstract.findall(".//p")]
        out["abstract"] = "\n".join(p for p in paras if p) or _text(abstract)
    body = root.find(".//body")
    if body is not None:
        for sec in body.findall("sec"):
            out["sections"].append({
                "title": _text(sec.find("title")),
                "paragraphs": [_text(p) for p in sec.iter("p") if _text(p)],
            })
        loose = [_text(p) for p in body.findall("p") if _text(p)]
        if loose:
            out["sections"].insert(0, {"title": "", "paragraphs": loose})
    return out


def sections_to_text(doc: Dict[str, Any]) -> str:
    parts: List[str] = []
    if doc.get("title"):
        parts.append(doc["title"])
    if doc.get("abstract"):
        parts.append("Abstract\n" + doc["abstract"])
    for sec in doc.get("sections", []):
        if sec.get("title"):
            parts.append(sec["title"])
        parts.extend(sec.get("paragraphs", []))
    return "\n\n".join(parts)


def download_pmc_fulltext(client: PubMedClient, records: Iterable[Dict[str, Any]], out_dir: Path,
                          overwrite: bool = False, limit: Optional[int] = None, save_txt: bool = True) -> Dict[str, int]:
    """Download JATS XML (and plain text) for each record with a PMCID. Returns counts."""
    from tqdm import tqdm

    out_dir = Path(out_dir)
    xml_dir, txt_dir = out_dir / "xml", out_dir / "txt"
    xml_dir.mkdir(parents=True, exist_ok=True)
    if save_txt:
        txt_dir.mkdir(parents=True, exist_ok=True)
    no_ft = out_dir / "no_fulltext.txt"
    already_no_ft = set(no_ft.read_text().split()) if no_ft.exists() else set()

    todo = [r for r in records if r.get("pmcid")]
    if limit:
        todo = todo[:limit]
    stats = {"candidates": len(todo), "downloaded": 0, "skipped_existing": 0, "no_fulltext": 0, "errors": 0}
    with open(no_ft, "a") as nf:
        for rec in tqdm(todo, desc="PMC full text", unit="paper"):
            pmcid = rec["pmcid"]
            dest = xml_dir / f"{pmcid}.xml"
            if (dest.exists() and not overwrite) or (pmcid in already_no_ft and not overwrite):
                stats["skipped_existing"] += 1
                continue
            try:
                xml_bytes = client.efetch_pmc_xml(pmcid)
            except Exception as e:  # noqa: BLE001
                log.warning("PMC fetch failed for %s: %s", pmcid, e)
                stats["errors"] += 1
                continue
            if not has_body(xml_bytes):
                stats["no_fulltext"] += 1
                nf.write(pmcid + "\n")
                nf.flush()
                continue
            dest.write_bytes(xml_bytes)
            if save_txt:
                try:
                    (txt_dir / f"{pmcid}.txt").write_text(sections_to_text(extract_sections(xml_bytes)), encoding="utf-8")
                except ET.ParseError:
                    log.warning("Could not extract text from %s", pmcid)
            stats["downloaded"] += 1
    return stats

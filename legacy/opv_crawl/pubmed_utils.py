"""
PubMed/PMC utilities for fetching papers
Adapted from existing biochem paper crawl scripts
"""

import os
import time
import requests
import xml.etree.ElementTree as ET
from typing import List, Union, Dict, Optional, Tuple
from Bio import Entrez

# Set up Entrez
Entrez.email = "heng6@illinois.edu"
Entrez.api_key = os.getenv("entrez_api_key")  # Optional: increases rate limit to 10/s

ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"

# Photostability and OPV-specific keywords
PHOTOSTABILITY_KEYWORDS = [
    "photostability", "photo-stability", "photodegradation", "photo-degradation",
    "photobleaching", "photo-bleaching", "photo-oxidation", "photooxidation",
    "light stability", "UV stability", "photochemical stability",
    "degradation under illumination", "light-induced degradation",
    "operational stability", "device lifetime"
]

OPV_KEYWORDS = [
    "organic photovoltaic", "OPV", "organic solar cell", "OSC",
    "bulk heterojunction", "BHJ", "polymer solar cell",
    "donor-acceptor", "active layer", "power conversion efficiency",
    "non-fullerene acceptor", "NFA", "conjugated polymer"
]

# Terms to exclude (not relevant to photostability)
EXCLUSION_TERMS = [
    "dye-sensitized solar cell", "DSSC", "perovskite solar cell",
    "silicon solar cell", "thin film solar cell",
    "clinical trial", "patient"
]


def get_pmcids_by_keywords(
    building_blocks: Union[str, List[str]], 
    max_results: int = 100,
    require_opv: bool = True,
    require_photostability: bool = True,
    relaxed_mode: bool = False
) -> Tuple[List[str], int, str]:
    """
    Search PMC for articles about OPV photostability with specific building blocks.
    
    Args:
        building_blocks: Building block name(s) to search for
        max_results: Maximum number of PMCIDs to return
        require_opv: If True, require OPV-related keywords
        require_photostability: If True, require photostability keywords
        relaxed_mode: If True, use simpler/broader query terms
    
    Returns:
        Tuple of (pmcid_list, total_count, query_string)
    """
    # Build building block query
    if isinstance(building_blocks, str):
        block_query = f'"{building_blocks}"[Title/Abstract]'
    else:
        block_query = " OR ".join([f'"{block}"[Title/Abstract]' for block in building_blocks])
    
    query_parts = [f"({block_query})"]
    
    # Add photostability requirement
    if require_photostability:
        if relaxed_mode:
            # Use fewer, more common terms
            simple_photo_terms = ['photostability', 'photodegradation', 'photobleaching', 'light stability']
            photo_query = " OR ".join([f'{term}[Title/Abstract]' for term in simple_photo_terms])
        else:
            photo_query = " OR ".join([f'"{term}"[Title/Abstract]' for term in PHOTOSTABILITY_KEYWORDS[:6]])
        query_parts.append(f"({photo_query})")
    
    # Add OPV requirement
    if require_opv:
        if relaxed_mode:
            # Use simpler, broader terms
            simple_opv_terms = ['solar cell', 'photovoltaic', 'organic solar', 'OPV']
            opv_query = " OR ".join([f'{term}[Title/Abstract]' for term in simple_opv_terms])
        else:
            opv_query = " OR ".join([f'"{term}"[Title/Abstract]' for term in OPV_KEYWORDS[:6]])
        query_parts.append(f"({opv_query})")
    
    # Add exclusions (lighter in relaxed mode)
    if not relaxed_mode:
        exclusion_query = " OR ".join([f'"{term}"' for term in EXCLUSION_TERMS])
        query = " AND ".join(query_parts) + f" NOT ({exclusion_query})"
    else:
        query = " AND ".join(query_parts)
    
    # Search PMC
    params = {
        "db": "pmc",
        "term": query,
        "retmax": max_results,
        "retmode": "json"
    }
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = requests.get(ESEARCH_URL, params=params, timeout=30)
            response.raise_for_status()
            break
        except requests.exceptions.RequestException as e:
            print(f"  Attempt {attempt + 1}/{max_retries} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(2)
            else:
                return [], 0, query
    
    result = response.json()["esearchresult"]
    id_list = result.get("idlist", [])
    total_count = int(result.get("count", 0))
    pmcids = [f"PMC{id_}" for id_ in id_list]
    
    return pmcids, total_count, query


def get_pmc_full_xml(
    pmcid: str, 
    email: Optional[str] = None, 
    api_key: Optional[str] = None
) -> Optional[str]:
    """
    Fetch full-text XML from PMC.
    
    Args:
        pmcid: PMC ID (e.g., "PMC3521743" or "3521743")
        email: Your email for NCBI (optional)
        api_key: Your NCBI API key (optional)
    
    Returns:
        Full XML string or None if error
    """
    if email:
        Entrez.email = email
    if api_key:
        Entrez.api_key = api_key
    
    # Clean PMCID
    pmcid = pmcid[3:] if pmcid.upper().startswith('PMC') else pmcid
    
    try:
        handle = Entrez.efetch(db="pmc", id=pmcid, rettype="full", retmode="xml")
        xml_data = handle.read().decode('utf-8')
        handle.close()
        return xml_data
    except Exception as e:
        print(f"  Error fetching PMC{pmcid}: {e}")
        return None


def get_pmc_full_xml_batch(
    pmcids: List[str], 
    email: Optional[str] = None, 
    api_key: Optional[str] = None,
    rate_limit: float = 0.2
) -> Dict[str, Optional[str]]:
    """
    Fetch full-text XML for multiple PMCIDs with rate limiting.
    
    Args:
        pmcids: List of PMC IDs
        email: Your email for NCBI
        api_key: Your NCBI API key
        rate_limit: Seconds between requests
    
    Returns:
        Dict mapping PMCID to XML string or None
    """
    results = {}
    for pmcid in pmcids:
        results[pmcid] = get_pmc_full_xml(pmcid, email=email, api_key=api_key)
        time.sleep(rate_limit)
    return results


def extract_text_from_pmc_xml(xml_string: str) -> str:
    """
    Extract text from <p> tags in PMC XML body.
    
    Args:
        xml_string: Full PMC XML content
    
    Returns:
        Concatenated text from all paragraphs
    """
    try:
        root = ET.fromstring(xml_string)
        body = root.find('.//body')
        
        if body is None:
            return "Could not find the <body> of the article."
        
        paragraphs = ["".join(p.itertext()) for p in body.findall('.//p')]
        return "\n\n".join(paragraphs)
    
    except ET.ParseError:
        return "Error parsing the XML string."


def extract_metadata_from_pmc_xml(xml_string: str) -> Dict:
    """
    Extract metadata (title, authors, journal, year, doi) from PMC XML.
    
    Args:
        xml_string: Full PMC XML content
    
    Returns:
        Dict with metadata fields
    """
    try:
        root = ET.fromstring(xml_string)
        metadata = {}
        
        # Title
        title_elem = root.find('.//article-title')
        metadata['title'] = "".join(title_elem.itertext()) if title_elem is not None else ""
        
        # Abstract
        abstract_elem = root.find('.//abstract')
        if abstract_elem is not None:
            metadata['abstract'] = "".join(abstract_elem.itertext())
        else:
            metadata['abstract'] = ""
        
        # Authors
        authors = []
        for author in root.findall('.//contrib[@contrib-type="author"]'):
            surname = author.find('.//surname')
            given_names = author.find('.//given-names')
            if surname is not None:
                name = surname.text or ""
                if given_names is not None:
                    name = f"{given_names.text} {name}"
                authors.append(name)
        metadata['authors'] = authors
        
        # Journal
        journal_elem = root.find('.//journal-title')
        metadata['journal'] = journal_elem.text if journal_elem is not None else ""
        
        # Year
        year_elem = root.find('.//pub-date/year')
        metadata['year'] = year_elem.text if year_elem is not None else ""
        
        # DOI
        doi_elem = root.find('.//article-id[@pub-id-type="doi"]')
        metadata['doi'] = doi_elem.text if doi_elem is not None else ""
        
        return metadata
    
    except ET.ParseError:
        return {'error': 'Error parsing XML'}


import requests
from typing import List, Union, Dict, Optional
from Bio import Entrez
import xml.etree.ElementTree as ET
import os

Entrez.email = "heng6@illinois.edu" # Set your email here
Entrez.api_key = os.getenv("entrez_api_key")  # Set your api key here to increase the rate limit to 10/s
ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"

def get_pmc_full_xml(pmcid: str, email: Optional[str] = None, api_key: Optional[str] = None) -> Optional[str]:
    """
    Fetches the full-text XML of a paper from the PMC database.
    Args:
        pmcid (str): The PMCID of the paper (e.g., "PMC3521743" or "3521743").
        email (str, optional): Your email address for NCBI Entrez. If None, uses global Entrez.email.
        api_key (str, optional): Your NCBI API key. If None, uses global Entrez.api_key.
    Returns:
        The full paper content as a raw XML string, or None if an error occurs.
    """
    if email:
        Entrez.email = email
    if api_key:
        Entrez.api_key = api_key
    # Sanitize PMCID input
    pmcid = pmcid[3:] if pmcid.upper().startswith('PMC') else pmcid
    # print(f"🚀 Fetching full-text XML for PMCID: {pmcid}...")
    try:
        handle = Entrez.efetch(db="pmc", id=pmcid, rettype="full", retmode="xml")
        # The XML content is encoded in UTF-8
        xml_data = handle.read().decode('utf-8')
        handle.close()
        # print("✅ Successfully fetched XML.")
        return xml_data
    except Exception as e:
        print(f"❌ An error occurred: {e}")
        return None

def get_pmc_full_xml_batch(pmcids: List[str], email: Optional[str] = None, api_key: Optional[str] = None) -> Dict[str, Optional[str]]:
    """
    Fetch full-text XML for a batch of PMCIDs. Returns a dict mapping pmcid to XML string or None.
    """
    results = {}
    for pmcid in pmcids:
        results[pmcid] = get_pmc_full_xml(pmcid, email=email, api_key=api_key)
    return results


def get_pmcids_by_keywords(medicine_names: Union[str, List[str]], max_results: int = 10) -> List[str]:
    """
    Search PMC for articles related to the given medicine name(s) and return a list of PMCIDs.
    Args:
        medicine_names (str or List[str]): Medicine name or list of medicine names to search for.
        max_results (int): Maximum number of PMCIDs to return.
    Returns:
        List[str]: List of PMCIDs as strings.
    """
    if isinstance(medicine_names, str):
        query = medicine_names
    else:
        query = " OR ".join(medicine_names)

    # Use ESearch to get PMC IDs
    params = {
        "db": "pmc",
        "term": query,
        "retmax": max_results,
        "retmode": "json"
    }
    esearch_resp = requests.get(ESEARCH_URL, params=params)
    esearch_resp.raise_for_status()
    id_list = esearch_resp.json()["esearchresult"].get("idlist", [])
    pmcids = [f"PMC{id_}" for id_ in id_list]
    return pmcids


def extract_title_abstract_body_from_pmc_xml(xml_string: str) -> dict:
    """
    Extracts the title, abstract, and body text from a PMC XML string.
    Returns a dict with 'title', 'abstract', and 'body'.
    """
    result = {'title': '', 'abstract': '', 'body': ''}
    try:
        root = ET.fromstring(xml_string)
        # Title
        title_elem = root.find('.//article-title')
        if title_elem is not None:
            result['title'] = ''.join(title_elem.itertext()).strip()
        # Abstract
        abstract_elem = root.find('.//abstract')
        if abstract_elem is not None:
            result['abstract'] = '\n'.join([''.join(p.itertext()).strip() for p in abstract_elem.findall('.//p')])
            if not result['abstract']:
                # Sometimes abstract is not in <p> tags
                result['abstract'] = ''.join(abstract_elem.itertext()).strip()
        # Body
        body_elem = root.find('.//body')
        if body_elem is not None:
            paragraphs = [
                ''.join(p.itertext()).strip() for p in body_elem.findall('.//p')
            ]
            result['body'] = '\n\n'.join(paragraphs)
    except ET.ParseError:
        pass
    return result

def extract_text_from_pmc_xml(xml_string: str) -> str:
    """
    Extract text from <p> tags within the <body> of a PMC XML string.
    Returns the concatenated text of all paragraphs.
    """
    try:
        root = ET.fromstring(xml_string)
        body = root.find('.//body')
        if body is None:
            return "Could not find the <body> of the article."
        paragraphs = [
            "".join(p.itertext()) for p in body.findall('.//p')
        ]
        return "\n\n".join(paragraphs)
    except ET.ParseError:
        return "Error parsing the XML string."
    
def get_pmc_fulltext_by_keywords(
    medicine_names: Union[str, List[str]],
    max_results: int = 10, 
    api_key: Optional[str] = None
    ) -> List[Dict]:
    """
    Search PMC for articles related to the given medicine name(s), fetch full content for open access articles.
    Args:
        medicine_names (str or List[str]): Medicine name or list of medicine names to search for.
        max_results (int): Maximum number of PMCIDs to return.
        api_key (str): Your NCBI API key. If None, uses global Entrez.api_key.
    Returns:
        List[Dict]: List of dicts with 'pmcid', 'title', 'abstract', and 'body'.
    """
    # get pmcids by keywords
    pmcids = get_pmcids_by_keywords(medicine_names, max_results)
    print(f"Found {len(pmcids)} PMCIDs {pmcids}")
    
    # get full xml by pmcids
    xml_dict = get_pmc_full_xml_batch(pmcids, api_key=api_key)
    # extract title, abstract, and body from xml
    results = []
    for pmcid, xml in xml_dict.items():
        if xml:
            extracted = extract_title_abstract_body_from_pmc_xml(xml)
            extracted['pmcid'] = pmcid
            results.append(extracted)
    return results
    
if __name__ == "__main__":
    # Run the test
    test_keywords = ["aspirin", "ibuprofen"]
    print(f"Fetching full content from PMC for keywords: {test_keywords}")
    papers = get_pmc_fulltext_by_keywords(test_keywords, max_results=2)
    for i, paper in enumerate(papers, 1):
        print(f"Paper {i}:")
        print(f"  PMCID   : {paper.get('pmcid')}")
        print(f"  Title   : {paper.get('title')[:100]}")
        print(f"  Abstract: {paper.get('abstract')[:200]}")
        print(f"  Body text snippet: {paper.get('body')[:1000]}{'...' if len(paper.get('body', '')) > 1000 else ''}")
        print("-" * 60)



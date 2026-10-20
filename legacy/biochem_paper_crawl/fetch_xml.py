import os
import json
from glob import glob
from tqdm import tqdm
import requests
from typing import List, Union, Dict, Optional
from Bio import Entrez
import xml.etree.ElementTree as ET
import os
import time
import xml.dom.minidom


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
    pmcids: List[str],
    basename: str,
    email: Optional[str] = None,
    api_key: Optional[str] = None
    ) -> List[Dict]:
    count = 0
    start_time = time.time()

    
    # get full xml by pmcids
    for pmcid in pmcids:
        if count >= 5:
            if time.time()-start_time < 1:
                time.sleep(1)
                start_time = time.time()
            count = 0
        xml_data = get_pmc_full_xml(pmcid, email=email, api_key=api_key)
        f_name = os.path.join('data_new/papers/' + basename, pmcid) + '.xml'
        if xml_data is None:
            continue
        dom = xml.dom.minidom.parseString(xml_data)
        pretty_xml = dom.toprettyxml()
        with open(f_name, 'w') as f:
            f.write(pretty_xml)
    

folder_path = "data_new/pmcids/"
all_dict = {}
json_files = glob(os.path.join(folder_path, "*.json"))
os.makedirs('data_new/papers', exist_ok=True)

for file in tqdm(json_files):
    basename = os.path.basename(file).rstrip('.json')
    with open(file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    pmcids = data['pmcids']
    os.makedirs('data_new/papers/' + basename, exist_ok=True)
    get_pmc_fulltext_by_keywords(pmcids, basename)
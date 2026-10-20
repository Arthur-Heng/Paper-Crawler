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

Entrez.email = "heng6@illinois.edu" # Set your email here
Entrez.api_key = os.getenv("entrez_api_key")  # Set your api key here to increase the rate limit to 10/s
ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"

    # "brand_name": [
    #     "Abacavir and Lamivudine"
    # ],
    # "generic_name": [
    #     "ABACAVIR AND LAMIVUDINE"
    # ],
    # "substance_name": [
    #     "ABACAVIR SULFATE",
    #     "LAMIVUDINE"
    # ],
# Chemistry-related keywords to ensure papers are about molecular properties
# Focus on specific molecular property measurements and assays
CHEMISTRY_KEYWORDS = [
    # Specific assays and measurements
    "IC50", "EC50", "Ki", "Kd", "LogP", "cLogP", 
    "aqueous solubility", "thermodynamic solubility",
    "liver microsomes", "microsomal stability",
    "Caco-2", "PAMPA", "Papp",
    "hERG inhibition", "hERG IC50",
    "AMES test", "AMES assay",
    # ADME terms (more specific)
    "ADME profiling", "ADME properties", "ADME assays",
    "CYP450 inhibition", "CYP3A4 inhibition", "CYP2D6",
    "plasma protein binding", "metabolic stability",
    "clearance", "half-life", "Cmax", "AUC",
    # BBB and permeability
    "blood-brain barrier penetration", "BBB permeability", "BBBP",
    "intestinal permeability", "membrane permeability",
    # Structure-activity
    "SAR", "structure-activity", "QSAR",
    "medicinal chemistry", "lead optimization",
    "drug design", "molecular design"
]

# Terms to EXCLUDE - indicate clinical rather than chemistry papers
CLINICAL_EXCLUSIONS = [
    "clinical trial", "randomized", "placebo",
    "case report", "case series", "patient",
    "cohort study", "retrospective study",
    "cost-effectiveness", "health outcomes"
]

def get_pmcids_by_keywords(medicine_names: Union[str, List[str]], max_results: int = 10, 
                           require_chemistry: bool = True) -> List[str]:
    """
    Search PMC for articles related to the given medicine name(s) and return a list of PMCIDs.
    This function ensures that:
    1. The drug name appears in the title or abstract, not just in references
    2. The paper discusses chemistry-related molecular properties (if require_chemistry=True)
    
    Args:
        medicine_names (str or List[str]): Medicine name or list of medicine names to search for.
        max_results (int): Maximum number of PMCIDs to return.
        require_chemistry (bool): If True, also require chemistry keywords in the paper.
    Returns:
        List[str]: List of PMCIDs as strings.
    """
    if isinstance(medicine_names, str):
        # Add [Title/Abstract] field tag to ensure the drug is in title or abstract
        drug_query = f"{medicine_names}[Title/Abstract]"
    else:
        # Use OR to combine multiple names, each restricted to Title/Abstract
        drug_query = " OR ".join([f"{name}[Title/Abstract]" for name in medicine_names])
    
    # Add chemistry filter if required
    if require_chemistry:
        # Combine chemistry keywords with OR (paper should mention at least one)
        chemistry_query = " OR ".join(CHEMISTRY_KEYWORDS)
        # Create NOT query for clinical terms to exclude
        exclusion_query = " OR ".join([f'"{term}"' for term in CLINICAL_EXCLUSIONS])
        # Combine: must have drug AND chemistry AND NOT clinical terms
        query = f"({drug_query}) AND ({chemistry_query}) NOT ({exclusion_query})"
    else:
        query = drug_query

    # Use ESearch to get PMC IDs
    params = {
        "db": "pmc",
        "term": query,
        "retmax": max_results,
        "retmode": "json"
    }
    while True:
        try:
            esearch_resp = requests.get(ESEARCH_URL, params=params)
            esearch_resp.raise_for_status()
            break
        except requests.exceptions.RequestException as e:
            print(f"Error: {e}")
            time.sleep(2)
            continue
        
    result = esearch_resp.json()["esearchresult"]
    id_list = result.get("idlist", [])
    total_count = int(result.get("count", 0))
    pmcids = [f"PMC{id_}" for id_ in id_list]
    return pmcids, total_count, query

folder_path = "data/fda_extraction_result/"
all_dict = {}
json_files = glob(os.path.join(folder_path, "*.json"))
max_results = 300

count = 0
os.makedirs('data_new/pmcids', exist_ok=True)
start_time = time.time()
for file in tqdm(json_files):
    basename = os.path.basename(file).replace('_pubchem_fda', '')

    if os.path.isfile('data_new/pmcids/' + basename):
        continue
    with open(file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    tmp = set()
    brand_name = data['brand_name']
    if isinstance(brand_name, str):
        tmp.add(brand_name)
    else:
        for name in brand_name:
            tmp.add(name)
    generic_name = data['generic_name']
    if isinstance(generic_name, str):
        tmp.add(generic_name)
    else:
        for name in generic_name:
            tmp.add(name)
    substance_name = data['substance_name']
    if isinstance(substance_name, str):
        tmp.add(substance_name)
    else:
        for name in substance_name:
            tmp.add(name)
    count += 1
    pmcids, total_count, query = get_pmcids_by_keywords(list(tmp), max_results)
    if len(pmcids) > 0:
        new_dict = {
            'pmcids': pmcids,
            'keywords': list(tmp),
            'total_count': total_count,
            'query': query
        }
        with open('data_new/pmcids/' + basename, 'w') as f:
            json.dump(new_dict, f, indent=4)

    if count >= 5:
        if time.time()-start_time < 1:
            time.sleep(1)
            start_time = time.time()
        count = 0

#!/usr/bin/env python3
"""
Paper Mining Script for OPV Photostability Studies

This script mines scientific papers reporting photostability of molecules 
containing specific building blocks for organic photovoltaics (OPVs).

Data sources:
1. Semantic Scholar API - Broad coverage, good API access
2. PubMed Central - Life sciences and chemistry focused
3. CrossRef - Metadata for journal articles

The script extracts building blocks from the Excel file and searches for 
papers mentioning photostability studies on these materials.
"""

import pandas as pd
import requests
import json
import time
from typing import List, Dict, Set
import re
from pathlib import Path
from datetime import datetime
import argparse
from tqdm import tqdm


class PaperMiner:
    """Class to mine papers from multiple sources"""
    
    def __init__(self, output_dir: str = "results"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        # API endpoints
        self.semantic_scholar_api = "https://api.semanticscholar.org/graph/v1/paper/search"
        self.pubmed_search_api = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        self.pubmed_fetch_api = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
        
        # Rate limiting
        self.last_request_time = 0
        self.min_request_interval = 1.0  # seconds
        
    def rate_limit(self):
        """Ensure we don't exceed API rate limits"""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)
        self.last_request_time = time.time()
    
    def extract_building_blocks(self, excel_path: str) -> List[Dict[str, str]]:
        """Extract building blocks from the Excel file"""
        print(f"Reading building blocks from {excel_path}")
        
        try:
            df = pd.read_csv(excel_path)
        except:
            # If CSV doesn't exist, try Excel
            df = pd.read_excel(excel_path)
        
        molecules = []
        for idx, row in df.iterrows():
            iupac_name = row['IUPAC Name (Abbreviated)']
            components = row['General Structural Components']
            
            # Parse building blocks
            building_blocks = [bb.strip() for bb in components.split(',')]
            
            molecules.append({
                'id': idx,
                'iupac_name': iupac_name,
                'building_blocks': building_blocks,
                'components_str': components
            })
        
        print(f"Loaded {len(molecules)} molecules with building blocks")
        return molecules
    
    def get_unique_building_blocks(self, molecules: List[Dict]) -> Set[str]:
        """Extract unique building blocks for searching"""
        all_blocks = set()
        for mol in molecules:
            for block in mol['building_blocks']:
                # Clean up block name (remove parentheses content and standardize)
                clean_block = re.sub(r'\([^)]*\)', '', block).strip()
                if clean_block and len(clean_block) > 3:  # Skip very short terms
                    all_blocks.add(clean_block)
        return all_blocks
    
    def search_semantic_scholar(self, query: str, limit: int = 100) -> List[Dict]:
        """Search Semantic Scholar for papers"""
        self.rate_limit()
        
        params = {
            'query': query,
            'limit': limit,
            'fields': 'paperId,title,abstract,authors,year,citationCount,publicationDate,journal,url'
        }
        
        try:
            response = requests.get(self.semantic_scholar_api, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            return data.get('data', [])
        except Exception as e:
            print(f"Error searching Semantic Scholar: {e}")
            return []
    
    def search_pubmed(self, query: str, max_results: int = 100) -> List[Dict]:
        """Search PubMed for papers"""
        self.rate_limit()
        
        # First, search for IDs
        search_params = {
            'db': 'pubmed',
            'term': query,
            'retmax': max_results,
            'retmode': 'json'
        }
        
        try:
            response = requests.get(self.pubmed_search_api, params=search_params, timeout=30)
            response.raise_for_status()
            search_data = response.json()
            
            id_list = search_data.get('esearchresult', {}).get('idlist', [])
            
            if not id_list:
                return []
            
            # Fetch details for each ID
            self.rate_limit()
            fetch_params = {
                'db': 'pubmed',
                'id': ','.join(id_list),
                'retmode': 'xml'
            }
            
            response = requests.get(self.pubmed_fetch_api, params=fetch_params, timeout=30)
            response.raise_for_status()
            
            # Parse XML response (simplified - you may want to use xml.etree.ElementTree)
            papers = []
            for pmid in id_list:
                papers.append({
                    'pmid': pmid,
                    'source': 'pubmed',
                    'url': f'https://pubmed.ncbi.nlm.nih.gov/{pmid}/'
                })
            
            return papers
            
        except Exception as e:
            print(f"Error searching PubMed: {e}")
            return []
    
    def mine_papers_for_building_blocks(self, building_blocks: Set[str], 
                                       search_terms: List[str] = None) -> Dict:
        """
        Mine papers mentioning photostability and building blocks
        
        Args:
            building_blocks: Set of building block names to search for
            search_terms: Additional search terms (default: photostability terms)
        """
        if search_terms is None:
            search_terms = [
                'photostability',
                'photo-stability',
                'photodegradation',
                'photo-degradation',
                'light stability',
                'photobleaching',
                'photo-oxidation'
            ]
        
        all_results = {
            'search_date': datetime.now().isoformat(),
            'building_blocks_searched': list(building_blocks),
            'photostability_terms': search_terms,
            'papers': []
        }
        
        print(f"\nMining papers for {len(building_blocks)} building blocks...")
        print(f"Photostability terms: {', '.join(search_terms)}")
        
        # Search for combinations of building blocks and photostability terms
        for block in tqdm(list(building_blocks)[:20], desc="Searching building blocks"):  # Limit to first 20 for demo
            for stability_term in search_terms:
                # Construct query
                query = f"{block} {stability_term} organic photovoltaic"
                
                # Search Semantic Scholar
                ss_papers = self.search_semantic_scholar(query, limit=20)
                
                for paper in ss_papers:
                    paper['building_block'] = block
                    paper['photostability_term'] = stability_term
                    paper['source'] = 'semantic_scholar'
                    all_results['papers'].append(paper)
                
                # Optional: Search PubMed (commented out to avoid rate limits)
                # pm_papers = self.search_pubmed(f"{block}[Title/Abstract] AND {stability_term}[Title/Abstract]", max_results=20)
                # for paper in pm_papers:
                #     paper['building_block'] = block
                #     paper['photostability_term'] = stability_term
                #     all_results['papers'].append(paper)
                
                # Small delay between searches
                time.sleep(0.5)
        
        return all_results
    
    def filter_relevant_papers(self, papers: List[Dict]) -> List[Dict]:
        """Filter papers to keep only most relevant ones"""
        relevant = []
        
        # Keywords that indicate photostability studies
        relevance_keywords = [
            'photostability', 'photodegradation', 'photo-stability',
            'light stability', 'photobleaching', 'degradation',
            'stability', 'lifetime', 'photo-oxidation', 'bleaching'
        ]
        
        for paper in papers:
            # Check title and abstract
            text = (paper.get('title', '') + ' ' + paper.get('abstract', '')).lower()
            
            if any(keyword in text for keyword in relevance_keywords):
                # Calculate relevance score
                score = sum(1 for keyword in relevance_keywords if keyword in text)
                paper['relevance_score'] = score
                relevant.append(paper)
        
        # Sort by relevance score and citation count
        relevant.sort(key=lambda x: (x.get('relevance_score', 0), 
                                     x.get('citationCount', 0)), 
                     reverse=True)
        
        return relevant
    
    def save_results(self, results: Dict, filename: str = None):
        """Save mining results to JSON file"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"photostability_papers_{timestamp}.json"
        
        output_path = self.output_dir / filename
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        print(f"\nResults saved to: {output_path}")
        return output_path
    
    def generate_summary_report(self, results: Dict):
        """Generate a summary report of the mining results"""
        papers = results['papers']
        
        # Remove duplicates (same paperId or title)
        unique_papers = {}
        for paper in papers:
            key = paper.get('paperId') or paper.get('title')
            if key and key not in unique_papers:
                unique_papers[key] = paper
        
        papers = list(unique_papers.values())
        
        # Filter for relevance
        relevant_papers = self.filter_relevant_papers(papers)
        
        print("\n" + "="*80)
        print("PAPER MINING SUMMARY")
        print("="*80)
        print(f"Total papers found: {len(papers)}")
        print(f"Relevant papers (filtered): {len(relevant_papers)}")
        print(f"Building blocks searched: {len(results['building_blocks_searched'])}")
        print(f"Photostability terms: {len(results['photostability_terms'])}")
        
        # Top papers by relevance
        print("\n" + "-"*80)
        print("TOP 10 MOST RELEVANT PAPERS:")
        print("-"*80)
        
        for i, paper in enumerate(relevant_papers[:10], 1):
            title = paper.get('title', 'No title')
            year = paper.get('year', 'N/A')
            citations = paper.get('citationCount', 0)
            relevance = paper.get('relevance_score', 0)
            url = paper.get('url', '')
            
            print(f"\n{i}. {title}")
            print(f"   Year: {year} | Citations: {citations} | Relevance: {relevance}")
            print(f"   Building Block: {paper.get('building_block', 'N/A')}")
            if url:
                print(f"   URL: {url}")
        
        # Save filtered results
        filtered_results = results.copy()
        filtered_results['papers'] = relevant_papers
        filtered_results['total_papers_found'] = len(papers)
        filtered_results['relevant_papers_count'] = len(relevant_papers)
        
        return filtered_results


def main():
    parser = argparse.ArgumentParser(
        description='Mine papers about photostability of OPV building blocks'
    )
    parser.add_argument(
        '--data',
        default='/shared/nas2/heng6/chem/opv/data/Common structural names for OPVs.xlsx',
        help='Path to Excel file with building blocks'
    )
    parser.add_argument(
        '--output-dir',
        default='results',
        help='Output directory for results'
    )
    parser.add_argument(
        '--max-blocks',
        type=int,
        default=20,
        help='Maximum number of building blocks to search (for testing)'
    )
    
    args = parser.parse_args()
    
    # Initialize miner
    miner = PaperMiner(output_dir=args.output_dir)
    
    # Load building blocks
    molecules = miner.extract_building_blocks(args.data)
    building_blocks = miner.get_unique_building_blocks(molecules)
    
    print(f"\nUnique building blocks identified: {len(building_blocks)}")
    print("Sample building blocks:")
    for block in list(building_blocks)[:10]:
        print(f"  - {block}")
    
    # Mine papers
    results = miner.mine_papers_for_building_blocks(building_blocks)
    
    # Generate summary and filter
    filtered_results = miner.generate_summary_report(results)
    
    # Save results
    miner.save_results(filtered_results)
    
    print("\n" + "="*80)
    print("Mining complete!")
    print("="*80)


if __name__ == "__main__":
    main()


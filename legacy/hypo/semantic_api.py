"""
Semantic Scholar API utilities for retrieving paper information and citations.
Limit: 1 request per second
"""

import os
import time
import json
import requests
from typing import Dict, List, Optional, Any


class SemanticScholarAPI:
    """Wrapper for Semantic Scholar API."""
    
    BASE_URL = "https://api.semanticscholar.org/graph/v1"
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the Semantic Scholar API client.
        
        Args:
            api_key: API key for Semantic Scholar. If None, will try to read from 
                    environment variable SEMANTIC_SCHOLAR_API_KEY.
        """
        self.api_key = api_key or os.getenv("SEMANTIC_SCHOLAR_API_KEY")
        self.headers = {}
        if self.api_key:
            self.headers["x-api-key"] = self.api_key
    
    def get_paper_by_title(self, title: str, fields: Optional[List[str]] = None, 
                           max_retries: int = 3) -> Optional[Dict[str, Any]]:
        """
        Search for a paper by its title and return the best match.
        
        Args:
            title: The title of the paper to search for.
            fields: List of fields to retrieve (e.g., ['title', 'authors', 'year', 'citationCount']).
                   If None, uses default fields.
            max_retries: Maximum number of retries for rate limiting (default: 3)
        
        Returns:
            Dictionary containing paper information, or None if not found.
        """
        if fields is None:
            fields = [
                'paperId', 'title', 'abstract', 'tldr', 'year', 'authors', 
                'citationCount', 'referenceCount', 'publicationDate',
                'venue', 'publicationTypes', 'externalIds', 'url', 'openAccessPdf'
            ]
        
        # Use the search endpoint
        search_url = f"{self.BASE_URL}/paper/search"
        params = {
            'query': title,
            'fields': ','.join(fields),
            'limit': 1  # Get the best match
        }
        
        for attempt in range(max_retries):
            try:
                response = requests.get(search_url, params=params, headers=self.headers)
                response.raise_for_status()
                
                data = response.json()
                if data.get('data') and len(data['data']) > 0:
                    return data['data'][0]
                else:
                    return None
                    
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:  # Rate limit
                    try:
                        retry_after = int(e.response.headers.get('Retry-After', 5))
                    except (ValueError, TypeError):
                        retry_after = 5
                    wait_time = max(retry_after, 2 ** attempt)  # Exponential backoff
                    print(f"  Rate limited. Waiting {wait_time}s before retry {attempt + 1}/{max_retries}...")
                    time.sleep(wait_time)
                    if attempt == max_retries - 1:
                        print(f"  Failed after {max_retries} retries")
                        return None
                elif e.response.status_code >= 500:  # Server error
                    wait_time = 2 ** attempt
                    print(f"  Server error {e.response.status_code}. Waiting {wait_time}s (retry {attempt + 1}/{max_retries})...")
                    time.sleep(wait_time)
                    if attempt == max_retries - 1:
                        print(f"  Failed after {max_retries} retries")
                        return None
                else:
                    print(f"Error searching for paper: {e}")
                    return None
            except requests.exceptions.RequestException as e:
                print(f"Error searching for paper: {e}")
                return None
        
        return None

    def get_paper_by_id(self, paper_id: str, fields: Optional[List[str]] = None,
                        max_retries: int = 3) -> Optional[Dict[str, Any]]:
        """
        Get a paper by its Semantic Scholar paper ID.

        Args:
            paper_id: The Semantic Scholar paper ID
            fields: List of fields to retrieve. If None, uses default fields.
            max_retries: Maximum number of retries for rate limiting (default: 3)

        Returns:
            Dictionary containing paper information, or None if not found.
        """
        if fields is None:
            fields = [
                'paperId', 'title', 'abstract', 'tldr', 'year', 'authors',
                'citationCount', 'referenceCount', 'publicationDate',
                'venue', 'publicationTypes', 'externalIds', 'url', 'openAccessPdf'
            ]

        url = f"{self.BASE_URL}/paper/{paper_id}"
        params = {'fields': ','.join(fields)}

        for attempt in range(max_retries):
            try:
                response = requests.get(url, params=params, headers=self.headers)
                response.raise_for_status()
                return response.json()

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 404:
                    # Paper not found
                    return None
                elif e.response.status_code == 429:  # Rate limit
                    try:
                        retry_after = int(e.response.headers.get('Retry-After', 5))
                    except (ValueError, TypeError):
                        retry_after = 5
                    wait_time = max(retry_after, 2 ** attempt)  # Exponential backoff
                    print(f"  Rate limited. Waiting {wait_time}s before retry {attempt + 1}/{max_retries}...")
                    time.sleep(wait_time)
                    if attempt == max_retries - 1:
                        print(f"  Failed after {max_retries} retries")
                        return None
                elif e.response.status_code >= 500:  # Server error
                    wait_time = 2 ** attempt
                    print(f"  Server error {e.response.status_code}. Waiting {wait_time}s (retry {attempt + 1}/{max_retries})...")
                    time.sleep(wait_time)
                    if attempt == max_retries - 1:
                        print(f"  Failed after {max_retries} retries")
                        return None
                else:
                    print(f"Error getting paper by ID: {e}")
                    return None
            except requests.exceptions.RequestException as e:
                print(f"Error getting paper by ID: {e}")
                return None

        return None

    def get_paper_citations(self, paper_id: str, limit: int = 100, fields: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Get citations for a paper (papers that cite this paper).
        
        Args:
            paper_id: The Semantic Scholar paper ID.
            limit: Maximum number of citations to retrieve (default 100, max 1000).
            fields: List of fields to retrieve for each citing paper.
                   If None, uses default fields.
        
        Returns:
            List of dictionaries containing information about citing papers.
        """
        if fields is None:
            fields = [
                'paperId', 'title', 'year', 'authors', 'citationCount',
                'publicationDate', 'venue'
            ]
        
        citations_url = f"{self.BASE_URL}/paper/{paper_id}/citations"
        params = {
            'fields': ','.join(fields),
            'limit': min(limit, 1000)  # API max is 1000
        }
        
        try:
            response = requests.get(citations_url, params=params, headers=self.headers)
            response.raise_for_status()
            
            data = response.json()
            # The API returns citations in the format: {'citingPaper': {...}}
            citations = []
            for item in data.get('data', []):
                if 'citingPaper' in item:
                    citations.append(item['citingPaper'])
            
            return citations
            
        except requests.exceptions.RequestException as e:
            print(f"Error retrieving citations: {e}")
            return []
    
    def get_paper_references(self, paper_id: str, limit: int = 100, fields: Optional[List[str]] = None, 
                            max_retries: int = 3) -> List[Dict[str, Any]]:
        """
        Get references for a paper (papers that this paper cites).
        
        Args:
            paper_id: The Semantic Scholar paper ID.
            limit: Maximum number of references to retrieve (default 100, max 1000).
            fields: List of fields to retrieve for each referenced paper.
                   If None, uses default fields.
            max_retries: Maximum number of retries for rate limiting (default: 3)
        
        Returns:
            List of dictionaries containing information about referenced papers.
        """
        if fields is None:
            fields = [
                'paperId', 'title', 'year', 'authors', 'citationCount',
                'publicationDate', 'venue'
            ]
        
        references_url = f"{self.BASE_URL}/paper/{paper_id}/references"
        params = {
            'fields': ','.join(fields),
            'limit': min(limit, 1000)  # API max is 1000
        }
        
        for attempt in range(max_retries):
            try:
                response = requests.get(references_url, params=params, headers=self.headers)
                response.raise_for_status()
                
                try:
                    data = response.json()
                except (ValueError, json.JSONDecodeError) as e:
                    print(f"  Error parsing JSON response: {e}")
                    if attempt == max_retries - 1:
                        return []
                    time.sleep(2 ** attempt)
                    continue
                
                if not data:
                    return []
                
                # The API returns references in the format: {'citedPaper': {...}}
                references = []
                data_list = data.get('data', [])
                
                # Handle case where API returns {"data": None}
                if data_list is None:
                    return []
                
                for item in data_list:
                    if item and 'citedPaper' in item:
                        references.append(item['citedPaper'])
                
                return references
                
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:  # Rate limit
                    try:
                        retry_after = int(e.response.headers.get('Retry-After', 5))
                    except (ValueError, TypeError):
                        retry_after = 5
                    wait_time = max(retry_after, 2 ** attempt)
                    print(f"  Rate limited getting references. Waiting {wait_time}s (retry {attempt + 1}/{max_retries})...")
                    time.sleep(wait_time)
                    if attempt == max_retries - 1:
                        print(f"  Failed after {max_retries} retries")
                        return []
                elif e.response.status_code >= 500:  # Server error
                    wait_time = 2 ** attempt
                    print(f"  Server error {e.response.status_code}. Waiting {wait_time}s (retry {attempt + 1}/{max_retries})...")
                    time.sleep(wait_time)
                    if attempt == max_retries - 1:
                        print(f"  Failed after {max_retries} retries")
                        return []
                else:
                    print(f"Error retrieving references: {e}")
                    return []
            except requests.exceptions.RequestException as e:
                print(f"Error retrieving references: {e}")
                if attempt == max_retries - 1:
                    return []
                time.sleep(2 ** attempt)
        
        return []
    
    def get_all_references_detailed(self, paper_id: str, max_results: Optional[int] = None, 
                                    rate_limit_delay: float = 1.1, fallback_to_simple: bool = True) -> List[Dict[str, Any]]:
        """
        Get ALL references for a paper with detailed fields including contexts, intents, and influence.
        This function handles pagination automatically and retrieves comprehensive information.
        
        Args:
            paper_id: The Semantic Scholar paper ID.
            max_results: Maximum number of references to retrieve. If None, gets all references.
            rate_limit_delay: Delay between paginated requests in seconds (default 1.1 for 1 req/sec limit).
        
        Returns:
            List of dictionaries containing detailed information about each reference, including:
            - citedPaper: The referenced paper details (paperId, title, authors, abstract, etc.)
            - contexts: List of contexts where the paper is cited (text snippets)
            - intents: List of citation intents (e.g., ['background'], ['methodology'], etc.)
            - isInfluential: Boolean indicating if this is an influential citation
        
        Example:
            >>> api = SemanticScholarAPI()
            >>> paper = api.get_paper_by_title("Attention is All You Need")
            >>> refs = api.get_all_references_detailed(paper['paperId'], max_results=50)
            >>> # Each reference contains:
            >>> ref = refs[0]
            >>> ref['citedPaper']['title']  # Title of the referenced paper
            >>> ref['contexts']  # List of text snippets where this paper is cited
            >>> ref['intents']  # Citation intents like 'background', 'methodology'
            >>> ref['isInfluential']  # True if this is marked as influential
        """
        # Comprehensive fields for references
        # Note: 'tldr' might not be available for all papers, but it's worth requesting
        fields = [
            # Citation context fields
            'contexts',
            'intents', 
            'isInfluential',
            # Cited paper fields
            'citedPaper.paperId',
            'citedPaper.title',
            'citedPaper.abstract',
            'citedPaper.year',
            'citedPaper.authors',
            'citedPaper.citationCount',
            'citedPaper.venue',
            'citedPaper.publicationTypes'
        ]
        
        references_url = f"{self.BASE_URL}/paper/{paper_id}/references"
        all_references = []
        offset = 0
        batch_size = 100  # Fetch 100 at a time
        
        print(f"Fetching references for paper {paper_id}...")
        
        while True:
            params = {
                'fields': ','.join(fields),
                'limit': batch_size,
                'offset': offset
            }
            
            # Retry logic for rate limiting
            max_retries = 3
            batch_data = None
            
            for attempt in range(max_retries):
                try:
                    response = requests.get(references_url, params=params, headers=self.headers)
                    response.raise_for_status()
                    
                    data = response.json()
                    batch_data = data.get('data', [])
                    break  # Success, exit retry loop
                    
                except requests.exceptions.HTTPError as e:
                    if e.response.status_code == 429:  # Rate limit
                        try:
                            retry_after = int(e.response.headers.get('Retry-After', 5))
                        except (ValueError, TypeError):
                            retry_after = 5
                        wait_time = max(retry_after, 2 ** attempt)
                        print(f"  Rate limited at offset {offset}. Waiting {wait_time}s (retry {attempt + 1}/{max_retries})...")
                        time.sleep(wait_time)
                        if attempt == max_retries - 1:
                            print(f"  Failed after {max_retries} retries, stopping...")
                            return all_references
                    elif e.response.status_code >= 500:  # Server error
                        wait_time = 2 ** attempt
                        print(f"  Server error {e.response.status_code} at offset {offset}. Waiting {wait_time}s (retry {attempt + 1}/{max_retries})...")
                        time.sleep(wait_time)
                        if attempt == max_retries - 1:
                            print(f"  Failed after {max_retries} retries, will try fallback...")
                            break  # Break to try fallback instead of returning
                    else:
                        print(f"Error retrieving references at offset {offset}: {e}")
                        break  # Break to try fallback
                except requests.exceptions.RequestException as e:
                    print(f"Error retrieving references at offset {offset}: {e}")
                    if attempt == max_retries - 1:
                        return all_references
                    time.sleep(2 ** attempt)
            
            if batch_data is None:
                # Error occurred, break to try fallback
                break
            
            if not batch_data:
                # No more results
                break
            
            # Debug: Check if we're getting the expected fields in the first batch
            if offset == 0 and batch_data:
                print(f"  [DEBUG] First reference keys: {list(batch_data[0].keys())}")
                if 'citedPaper' in batch_data[0]:
                    print(f"  [DEBUG] citedPaper keys: {list(batch_data[0]['citedPaper'].keys())[:10]}")
            
            # Add the batch to our results
            all_references.extend(batch_data)
            
            print(f"  Retrieved {len(all_references)} references so far...")
            
            # Check if we've reached max_results or end of data
            if max_results and len(all_references) >= max_results:
                all_references = all_references[:max_results]
                break
            
            # Check if we got fewer results than requested (means we're at the end)
            if len(batch_data) < batch_size:
                break
            
            offset += batch_size
            
            # Rate limiting: wait before next request
            time.sleep(rate_limit_delay)
        
        print(f"✓ Retrieved {len(all_references)} total references")
        
        # If no references retrieved and fallback is enabled, try simple endpoint
        if not all_references and fallback_to_simple:
            print(f"\n⚠ Detailed endpoint failed, falling back to simple references endpoint...")
            time.sleep(rate_limit_delay)
            
            simple_refs = self.get_paper_references(paper_id, limit=max_results or 1000)
            if simple_refs:
                print(f"✓ Retrieved {len(simple_refs)} references from simple endpoint")
                # Convert simple format to detailed format structure
                all_references = []
                for ref in simple_refs:
                    all_references.append({
                        'citedPaper': ref,
                        'contexts': [],
                        'intents': [],
                        'isInfluential': False  # Unknown, assume false
                    })
        
        return all_references
    
    def analyze_references(self, references: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Analyze detailed references to extract insights.
        
        Args:
            references: List of reference dictionaries from get_all_references_detailed().
        
        Returns:
            Dictionary containing analysis results including:
            - total_references: Total number of references
            - influential_count: Number of influential citations
            - intent_distribution: Count of each citation intent/type (background, methodology, result, etc.)
            - references_with_context: Number of references with citation contexts
            - references_by_intent: References grouped by their citation intent
            - top_cited: Most cited referenced papers
        """
        analysis = {
            'total_references': len(references),
            'influential_count': 0,
            'intent_distribution': {},
            'references_with_context': 0,
            'references_by_intent': {},  # Group references by intent type
            'references_without_intent': 0,
            'top_cited': [],
            'has_abstract': 0,
            'has_pdf': 0,
            'publication_type_distribution': {}
        }
        
        cited_papers = []
        
        for ref in references:
            # Count influential citations
            if ref.get('isInfluential'):
                analysis['influential_count'] += 1
            
            # Count references with contexts
            if ref.get('contexts'):
                analysis['references_with_context'] += 1
            
            # Count citation intents and group references by intent
            intents = ref.get('intents', [])
            if intents:
                for intent in intents:
                    # Count intent distribution
                    analysis['intent_distribution'][intent] = analysis['intent_distribution'].get(intent, 0) + 1
                    
                    # Group references by intent
                    if intent not in analysis['references_by_intent']:
                        analysis['references_by_intent'][intent] = []
                    
                    cited_paper = ref.get('citedPaper', {})
                    analysis['references_by_intent'][intent].append({
                        'title': cited_paper.get('title', 'N/A'),
                        'year': cited_paper.get('year', 'N/A'),
                        'paperId': cited_paper.get('paperId'),
                        'isInfluential': ref.get('isInfluential', False)
                    })
            else:
                analysis['references_without_intent'] += 1
            
            # Collect cited paper info
            cited_paper = ref.get('citedPaper', {})
            if cited_paper:
                if cited_paper.get('abstract'):
                    analysis['has_abstract'] += 1
                if cited_paper.get('openAccessPdf'):
                    analysis['has_pdf'] += 1
                
                cited_papers.append({
                    'title': cited_paper.get('title', 'N/A'),
                    'year': cited_paper.get('year', 'N/A'),
                    'citations': cited_paper.get('citationCount', 0),
                    'paperId': cited_paper.get('paperId')
                })
        
        # Sort by citation count and get top 10
        cited_papers.sort(key=lambda x: x['citations'], reverse=True)
        analysis['top_cited'] = cited_papers[:10]
        
        return analysis
    
    def filter_references_by_intent(self, references: List[Dict[str, Any]], intent: str) -> List[Dict[str, Any]]:
        """
        Filter references by citation intent/type.
        
        Args:
            references: List of reference dictionaries from get_all_references_detailed().
            intent: Citation intent to filter by (e.g., 'background', 'methodology', 'result').
        
        Returns:
            List of references matching the specified intent.
        
        Example:
            >>> refs = api.get_all_references_detailed(paper_id)
            >>> background_refs = api.filter_references_by_intent(refs, 'background')
            >>> methodology_refs = api.filter_references_by_intent(refs, 'methodology')
        """
        filtered = []
        for ref in references:
            intents = ref.get('intents', [])
            if intent in intents:
                filtered.append(ref)
        return filtered
    
    def download_paper(self, paper: Dict[str, Any], output_dir: str = ".", filename: Optional[str] = None, try_arxiv: bool = True) -> Optional[str]:
        """
        Download a paper's PDF if available.
        
        Args:
            paper: Paper dictionary (should contain 'openAccessPdf' and/or 'externalIds').
                  You can get this from get_paper_by_title().
            output_dir: Directory to save the PDF (default: current directory).
            filename: Custom filename for the PDF. If None, uses paper title.
            try_arxiv: If True, will try to download from ArXiv if openAccessPdf is not available.
        
        Returns:
            Path to the downloaded PDF file, or None if PDF not available or download failed.
        """
        pdf_url = None
        source = None
        
        # First, try open access PDF from Semantic Scholar
        open_access_pdf = paper.get('openAccessPdf')
        if open_access_pdf and open_access_pdf.get('url'):
            pdf_url = open_access_pdf['url']
            source = "Semantic Scholar Open Access"
        
        # If no open access PDF, try ArXiv
        if not pdf_url and try_arxiv:
            external_ids = paper.get('externalIds', {})
            if external_ids and 'ArXiv' in external_ids:
                arxiv_id = external_ids['ArXiv']
                pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
                source = "ArXiv"
                print(f"No open access PDF in Semantic Scholar, trying ArXiv ID: {arxiv_id}")
        
        # If still no URL found, give up
        if not pdf_url:
            print(f"No PDF source available for: {paper.get('title', 'Unknown')}")
            print(f"  Checked: Semantic Scholar Open Access, ArXiv")
            external_ids = paper.get('externalIds', {})
            if external_ids:
                print(f"  Available IDs: {', '.join(external_ids.keys())}")
            return None
        
        # Generate filename
        if filename is None:
            # Use paper title, sanitize for filesystem
            title = paper.get('title', 'paper')
            # Remove or replace characters that are problematic in filenames
            sanitized_title = "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in title)
            sanitized_title = sanitized_title.strip()[:100]  # Limit length
            filename = f"{sanitized_title}.pdf"
        
        if not filename.endswith('.pdf'):
            filename += '.pdf'
        
        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, filename)
        
        try:
            print(f"Downloading PDF from {source}: {pdf_url}")
            response = requests.get(pdf_url, stream=True, timeout=30)
            response.raise_for_status()
            
            # Write PDF to file
            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            file_size = os.path.getsize(output_path)
            print(f"✓ PDF downloaded successfully: {output_path} ({file_size / 1024 / 1024:.2f} MB)")
            return output_path
            
        except requests.exceptions.RequestException as e:
            print(f"Error downloading PDF: {e}")
            return None
        except IOError as e:
            print(f"Error saving PDF: {e}")
            return None


def test_semantic_scholar_api():
    """Test the Semantic Scholar API functions."""
    print("=" * 80)
    print("Testing Semantic Scholar API")
    print("=" * 80)
    
    # Initialize the API client
    api = SemanticScholarAPI()
    
    # Test 1: Search for a well-known paper
    print("\n[Test 1] Searching for paper by title...")
    title = "Attention is All You Need"
    title = "Can Language Models Solve Graph Problems in Natural Language?"
    paper = api.get_paper_by_title(title)
    
    if paper:
        print(f"✓ Found paper: {paper['title']}")
        print(f"  - Authors: {', '.join([a['name'] for a in paper.get('authors', [])])}")
        print(f"  - Year: {paper.get('year')}")
        print(f"  - Citation count: {paper.get('citationCount')}")
        print(f"  - Paper ID: {paper.get('paperId')}")
        print(f"  - URL: {paper.get('url')}")
        
        # Wait to respect rate limit (1 request per second)
        time.sleep(1.1)
        
        # Test 2: Get citations for this paper
        print("\n[Test 2] Getting citations for this paper...")
        paper_id = paper['paperId']
        citations = api.get_paper_citations(paper_id, limit=5)
        
        print(f"✓ Found {len(citations)} citations (showing first 5):")
        for i, citation in enumerate(citations, 1):
            print(f"  {i}. {citation.get('title')} ({citation.get('year')})")
        
        # Wait to respect rate limit (1 request per second)
        time.sleep(1.1)
        
        # Test 3: Get references for this paper
        print("\n[Test 3] Getting references cited by this paper...")
        references = api.get_paper_references(paper_id, limit=5)
        
        print(f"✓ Found {len(references)} references (showing first 5):")
        for i, reference in enumerate(references, 1):
            print(f"  {i}. {reference.get('title')} ({reference.get('year')})")
        
        # Wait to respect rate limit
        time.sleep(1.1)
        
        # Test 4: Get detailed references with contexts and intents
        print("\n[Test 4] Getting detailed references (first 20 with contexts/intents)...")
        detailed_refs = api.get_all_references_detailed(paper_id, max_results=20)
        if detailed_refs:
            print(f"\n✓ Retrieved {len(detailed_refs)} detailed references")
            
            # Debug: Show raw structure of first reference
            print("\n  [DEBUG] Raw structure of first reference:")
            if detailed_refs:
                print(json.dumps(detailed_refs[0], indent=2, default=str)[:800])
            
            print("\nShowing first 3 with details:")
            for i, ref in enumerate(detailed_refs[:3], 1):
                cited_paper = ref.get('citedPaper', {})
                print(f"\n  {i}. {cited_paper.get('title', 'N/A')} ({cited_paper.get('year', 'N/A')})")
                
                # Show publication type
                pub_types = cited_paper.get('publicationTypes', [])
                if pub_types:
                    print(f"     - Type: {', '.join(pub_types)}")
                else:
                    print(f"     - Type: Unknown")
                
                # Show venue
                venue = cited_paper.get('venue')
                if venue:
                    print(f"     - Venue: {venue}")
                
                print(f"     - Influential: {ref.get('isInfluential', False)}")
                
                # Debug intents
                intents = ref.get('intents', [])
                print(f"     - Intents: {intents if intents else '(empty)'}")
                
                print(f"     - Citation Count: {cited_paper.get('citationCount', 0)}")
                
                contexts = ref.get('contexts', [])
                if contexts:
                    print(f"     - Contexts ({len(contexts)}): {contexts[0][:100]}..." if len(contexts[0]) > 100 else f"     - Contexts: {contexts[0]}")
                else:
                    print(f"     - Contexts: None")
            
            # Analyze the references
            print("\n  Analyzing references...")
            analysis = api.analyze_references(detailed_refs)
            print(f"\n  Analysis Summary:")
            print(f"    - Total references: {analysis['total_references']}")
            print(f"    - Influential citations: {analysis['influential_count']} ({analysis['influential_count']/analysis['total_references']*100:.1f}%)")
            print(f"    - With citation contexts: {analysis['references_with_context']} ({analysis['references_with_context']/analysis['total_references']*100:.1f}%)")
            print(f"    - Without intents: {analysis['references_without_intent']} ({analysis['references_without_intent']/analysis['total_references']*100:.1f}%)")
            print(f"    - With abstracts: {analysis['has_abstract']} ({analysis['has_abstract']/analysis['total_references']*100:.1f}%)")
            print(f"    - With PDFs: {analysis['has_pdf']} ({analysis['has_pdf']/analysis['total_references']*100:.1f}%)")
            
            # Show citation intent/type distribution
            if analysis['intent_distribution']:
                print(f"\n  Citation Types (Intents) Distribution:")
                for intent, count in sorted(analysis['intent_distribution'].items(), key=lambda x: x[1], reverse=True):
                    print(f"    - {intent}: {count} ({count/analysis['total_references']*100:.1f}%)")
                
                # Show examples for each intent type
                print(f"\n  Example references by citation type:")
                for intent in list(analysis['references_by_intent'].keys())[:3]:  # Show first 3 types
                    refs_of_type = analysis['references_by_intent'][intent]
                    print(f"    {intent.upper()} ({len(refs_of_type)} refs):")
                    for ref_info in refs_of_type[:2]:  # Show 2 examples per type
                        influential_mark = "★" if ref_info['isInfluential'] else " "
                        print(f"      {influential_mark} {ref_info['title'][:60]}... ({ref_info['year']})")
            else:
                print(f"    - No citation intent information available")
            
            print(f"\n  Top 3 most cited references:")
            for i, paper_info in enumerate(analysis['top_cited'][:3], 1):
                print(f"    {i}. {paper_info['title'][:60]}... ({paper_info['year']}) - {paper_info['citations']} citations")
        
        # Test 5: Download the paper (will try ArXiv if no open access PDF)
        # print("\n[Test 5] Attempting to download paper PDF...")
        # pdf_path = api.download_paper(paper, output_dir="/tmp/papers")
        
        # if not pdf_path:
        #     print("  Could not download 'Attention is All You Need'")
        #     print("\n  Trying another paper...")
        #     time.sleep(1.1)
        #     another_paper = api.get_paper_by_title("BERT: Pre-training of Deep Bidirectional Transformers")
        #     if another_paper:
        #         pdf_path = api.download_paper(another_paper, output_dir="/tmp/papers")
    else:
        print("✗ Paper not found")
    
    print("\n" + "=" * 80)
    print("Tests completed!")
    print("=" * 80)


if __name__ == "__main__":
    test_semantic_scholar_api()


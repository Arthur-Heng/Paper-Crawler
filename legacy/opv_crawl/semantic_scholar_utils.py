"""
Semantic Scholar API utilities
"""

import os
import time
import requests
from typing import List, Dict, Optional


SEMANTIC_SCHOLAR_API = "https://api.semanticscholar.org/graph/v1/paper/search"
SEMANTIC_SCHOLAR_PAPER_API = "https://api.semanticscholar.org/graph/v1/paper"

# Get API key from environment
SEMANTIC_SCHOLAR_API_KEY = os.getenv("SEMANTIC_SCHOLAR_API_KEY") or os.getenv("S2_API_KEY")

# Rate limiting
_last_request_time = 0
# With API key: 100 requests per 5 minutes = 1 per 3 seconds safe
# Without API key: More conservative rate limit
MIN_REQUEST_INTERVAL = 1.0 if SEMANTIC_SCHOLAR_API_KEY else 3.0  # seconds


def _get_headers():
    """Get headers for API requests"""
    headers = {}
    if SEMANTIC_SCHOLAR_API_KEY:
        headers['x-api-key'] = SEMANTIC_SCHOLAR_API_KEY
    return headers


def _rate_limit():
    """Ensure we don't exceed Semantic Scholar rate limits"""
    global _last_request_time
    elapsed = time.time() - _last_request_time
    if elapsed < MIN_REQUEST_INTERVAL:
        time.sleep(MIN_REQUEST_INTERVAL - elapsed)
    _last_request_time = time.time()


def search_semantic_scholar(
    query: str,
    limit: int = 100,
    year_range: Optional[tuple] = None
) -> List[Dict]:
    """
    Search Semantic Scholar for papers.
    
    Args:
        query: Search query string
        limit: Maximum number of results (max 100 per request)
        year_range: Optional tuple of (min_year, max_year)
    
    Returns:
        List of paper dictionaries
    """
    _rate_limit()
    
    params = {
        'query': query,
        'limit': min(limit, 100),
        'fields': 'paperId,title,abstract,authors,year,citationCount,publicationDate,journal,url,venue,externalIds,isOpenAccess'
    }
    
    if year_range:
        params['year'] = f"{year_range[0]}-{year_range[1]}"
    
    headers = _get_headers()
    
    try:
        response = requests.get(SEMANTIC_SCHOLAR_API, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        return data.get('data', [])
    
    except Exception as e:
        print(f"  Error searching Semantic Scholar: {e}")
        return []


def get_paper_details(paper_id: str, id_type: str = "paperId") -> Optional[Dict]:
    """
    Get detailed information about a specific paper.
    
    Args:
        paper_id: Paper ID (can be Semantic Scholar ID, DOI, arXiv ID, etc.)
        id_type: Type of ID ("paperId", "DOI", "ArXiv", etc.)
    
    Returns:
        Paper dictionary or None
    """
    _rate_limit()
    
    url = f"{SEMANTIC_SCHOLAR_PAPER_API}/{paper_id}"
    params = {
        'fields': 'paperId,title,abstract,authors,year,citationCount,publicationDate,journal,url,venue,externalIds,isOpenAccess,references,citations'
    }
    
    headers = _get_headers()
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()
    
    except Exception as e:
        print(f"  Error fetching paper details: {e}")
        return None


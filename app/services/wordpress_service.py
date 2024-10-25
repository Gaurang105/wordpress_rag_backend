import requests
import logging
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
from datetime import datetime

logger = logging.getLogger(__name__)

class WordPressService:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip('/')
        if not self.base_url.endswith('/wp-json/wp/v2'):
            self.base_url = f"{self.base_url}/wp-json/wp/v2"

    async def fetch_content(self, per_page: int = 100) -> List[Dict]:
        """Fetch all posts and pages."""
        all_content = []
        
        try:
            # Fetch posts
            page = 1
            while True:
                response = requests.get(
                    f"{self.base_url}/posts",
                    params={
                        "page": page,
                        "per_page": per_page,
                        "status": "publish",
                        "_fields": "id,content,title,modified,link"
                    }
                )
                
                if response.status_code == 400:
                    break
                    
                response.raise_for_status()
                posts = response.json()
                
                if not posts:
                    break
                    
                all_content.extend(posts)
                page += 1
                
            logger.info(f"Successfully fetched {len(all_content)} posts")
            return all_content
            
        except requests.RequestException as e:
            logger.error(f"Error fetching WordPress content: {str(e)}")
            raise

    def clean_content(self, html_content: str) -> str:
        """Clean HTML content."""
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Remove script and style elements
        for element in soup(['script', 'style', 'iframe']):
            element.decompose()
            
        text = soup.get_text(separator=' ', strip=True)
        return ' '.join(text.split())

    async def get_modified_content(
        self,
        since: Optional[datetime] = None
    ) -> List[Dict]:
        """Get content modified since specified datetime."""
        try:
            params = {
                "per_page": 100,
                "status": "publish",
                "_fields": "id,content,title,modified,link"
            }
            
            if since:
                params["modified_after"] = since.isoformat()
                
            response = requests.get(
                f"{self.base_url}/posts",
                params=params
            )
            response.raise_for_status()
            
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching modified content: {str(e)}")
            return []
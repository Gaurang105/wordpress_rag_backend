import requests
import nltk
from nltk.tokenize import sent_tokenize
from sentence_transformers import SentenceTransformer
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Union
import logging
import json
import asyncio
from tenacity import retry, stop_after_attempt, wait_exponential

# Initialize logging and NLTK
logger = logging.getLogger(__name__)
nltk.download('punkt', quiet=True)

# Initialize the sentence transformer model
model = SentenceTransformer('all-MiniLM-L6-v2')

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10)
)
def fetch_wordpress_posts(wp_posts_url: str, per_page: int = 100) -> List[Dict]:
    """
    Fetch all posts from a WordPress site with retry logic.
    """
    all_posts = []
    page = 1
    
    while True:
        try:
            url = f"{wp_posts_url}?per_page={per_page}&page={page}&_fields=id,content,title,modified,link"
            response = requests.get(
                url,
                headers={'User-Agent': 'WordPress-RAG-Bot/1.0'},
                timeout=30
            )
            
            if response.status_code == 400:
                break
                
            response.raise_for_status()
            posts = response.json()
            
            if not posts:
                break
                
            all_posts.extend(posts)
            page += 1
            
        except requests.RequestException as e:
            logger.error(f"Error fetching posts: {str(e)}")
            break
    
    logger.info(f"Total posts fetched: {len(all_posts)}")
    return all_posts

def posts_are_equal(post1: Dict, post2: Dict) -> bool:
    """Compare two posts to check if they are the same version."""
    return (
        str(post1['id']) == str(post2['id']) and 
        post1['modified'] == post2['modified']
    )

def clean_html_content(html_content: str) -> str:
    """Clean HTML content and extract meaningful text."""
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Remove script and style elements
    for script in soup(["script", "style"]):
        script.decompose()
    
    # Get text and clean it
    text = soup.get_text(separator=' ', strip=True)
    
    # Remove extra whitespace
    text = ' '.join(text.split())
    
    return text

def chunk_posts(
    posts: List[Dict],
    max_chunk_size: int = 1000,
    overlap: int = 100
) -> List[Dict]:
    """Split posts into overlapping chunks for better context preservation."""
    chunked_posts = []
    
    for post in posts:
        try:
            # Clean and extract text
            text = clean_html_content(post['content']['rendered'])
            sentences = sent_tokenize(text)
            
            chunks = []
            current_chunk = []
            current_size = 0
            
            for sentence in sentences:
                sentence_size = len(sentence)
                
                if current_size + sentence_size > max_chunk_size and current_chunk:
                    # Join current chunk and add to chunks
                    chunk_text = ' '.join(current_chunk)
                    chunks.append(chunk_text)
                    
                    # Keep some sentences for overlap
                    overlap_text = ' '.join(current_chunk[-2:])  # Keep last 2 sentences
                    current_chunk = [overlap_text, sentence]
                    current_size = len(overlap_text) + sentence_size
                else:
                    current_chunk.append(sentence)
                    current_size += sentence_size
            
            # Add the last chunk if it exists
            if current_chunk:
                chunks.append(' '.join(current_chunk))
            
            chunked_posts.append({
                "id": post["id"],
                "title": post['title']['rendered'],
                "url": post['link'],
                "chunks": chunks
            })
            
        except Exception as e:
            logger.error(f"Error chunking post {post.get('id', 'unknown')}: {str(e)}")
            continue
    
    return chunked_posts

def embed_query(text: str) -> List[float]:
    """Generate embeddings for a text using SentenceTransformer."""
    try:
        return model.encode(text).tolist()
    except Exception as e:
        logger.error(f"Error generating embedding: {str(e)}")
        raise

def similarity_search(
    query_vector: List[float],
    collection,
    top_k: int = 5
) -> Dict[str, Any]:
    """Search for similar chunks in ChromaDB collection."""
    try:
        results = collection.query(
            query_embeddings=[query_vector],
            n_results=top_k,
            include=['documents', 'metadatas', 'distances']
        )
        return results
    except Exception as e:
        logger.error(f"Error in similarity search: {str(e)}")
        raise

def get_context(
    results: Dict[str, Any],
    max_chunks: int = 3,
) -> List[Dict]:
    """Extract and filter context from search results."""
    context = []
    try:
        if results and 'documents' in results and results['documents']:
            documents = results['documents'][0]  # First query result
            metadatas = results.get('metadatas', [[]])[0]
            distances = results.get('distances', [[]])[0]
            
            for i, (doc, metadata, distance) in enumerate(zip(documents, metadatas, distances)):
                if i >= max_chunks:
                    break
                    
                context.append({
                    'content': doc,
                    'title': metadata.get('title', ''),
                    'url': metadata.get('url', ''),
                    'relevance_score': 1 / (1 + distance)  # Convert distance to similarity score
                })
        return context
    except Exception as e:
        logger.error(f"Error processing context: {str(e)}")
        return []

def augment_query(
    query: str,
    context: List[Dict],
) -> str:
    """Augment user query with context."""
    if not context:
        formatted_context = "No specific context found."
    else:
        formatted_context = "\n\n".join([
            f"Title: {ctx['title']}\n"
            f"Relevance: {ctx.get('relevance_score', 0):.2f}\n"
            f"Content: {ctx['content']}\n"
            f"Source: {ctx['url']}"
            for ctx in context
        ])
    
    return f"""Context from website: {formatted_context}
        
        Current query: {query}"""

async def update_chroma_index(
    collection,
    chunked_posts: List[Dict],
    batch_size: int = 100
) -> None:
    """Update ChromaDB index with new chunks in batches."""
    try:
        total_chunks = sum(len(post['chunks']) for post in chunked_posts)
        logger.info(f"Preparing to index {total_chunks} chunks from {len(chunked_posts)} posts")
        
        for post in chunked_posts:
            embeddings = []
            documents = []
            ids = []
            metadatas = []
            
            for i, chunk in enumerate(post['chunks']):
                # Generate embedding
                embeddings.append(embed_query(chunk))
                documents.append(chunk)
                ids.append(f"{post['id']}_{i}")
                metadatas.append({
                    "title": post['title'],
                    "url": post['url'],
                    "post_id": post['id']
                })
            
            # Batch upsert
            for i in range(0, len(documents), batch_size):
                batch_end = min(i + batch_size, len(documents))
                collection.upsert(
                    embeddings=embeddings[i:batch_end],
                    documents=documents[i:batch_end],
                    ids=ids[i:batch_end],
                    metadatas=metadatas[i:batch_end]
                )
                
                logger.debug(f"Indexed batch of {batch_end - i} chunks")
                await asyncio.sleep(0.1)  # Prevent overloading
        
        logger.info(f"Successfully updated ChromaDB index with {total_chunks} chunks")
    except Exception as e:
        logger.error(f"Error updating ChromaDB index: {str(e)}")
        raise
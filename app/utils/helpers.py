import requests
import nltk
from nltk.tokenize import sent_tokenize
from sentence_transformers import SentenceTransformer
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Tuple
import logging

# Set up logging and NLTK
logger = logging.getLogger(__name__)
nltk.download('punkt', quiet=True)

model = SentenceTransformer('all-MiniLM-L6-v2')

def fetch_wordpress_posts(wp_posts_url: str, per_page: int = 100) -> List[Dict]:
    """Fetch all posts from a WordPress site using the complete WP REST API URL."""
    all_posts = []
    page = 1
    
    while True:
        try:
            url = f"{wp_posts_url}?per_page={per_page}&page={page}&_fields=id,content,title,modified,link"
            response = requests.get(url)
            
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
        post1['id'] == post2['id'] and 
        post1['modified'] == post2['modified']
    )

def chunk_posts(posts: List[Dict], max_chunk_size: int = 1000) -> List[Dict]:
    """Split posts into chunks for processing."""
    chunked_posts = []
    for post in posts:
        soup = BeautifulSoup(post['content']['rendered'], 'html.parser')
        text = soup.get_text(separator=' ', strip=True)
        sentences = sent_tokenize(text)
        
        chunks = []
        current_chunk = ""
        
        for sentence in sentences:
            if len(current_chunk) + len(sentence) > max_chunk_size and current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = sentence
            else:
                current_chunk += " " + sentence
        
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        chunked_posts.append({
            "id": post["id"],
            "title": post['title']['rendered'],
            "url": post['link'],
            "chunks": chunks
        })
    
    return chunked_posts

def embed_query(text: str) -> List[float]:
    """Generate embeddings for a text using SentenceTransformer."""
    return model.encode(text).tolist()

def similarity_search(query_vector: List[float], collection, top_k: int = 5) -> Dict:
    """Search for similar chunks in ChromaDB collection."""
    try:
        results = collection.query(
            query_embeddings=[query_vector],
            n_results=top_k
        )
        return results
    except Exception as e:
        logger.error(f"Error in similarity search: {str(e)}")
        raise

def get_context(results: Dict, max_chunks: int = 3) -> List[Dict]:
    """Extract context from search results."""
    context = []
    try:
        if results and 'documents' in results and results['documents']:
            documents = results['documents'][0]  # First query result
            metadatas = results.get('metadatas', [[]])[0]  # First query metadata
            
            for i, doc in enumerate(documents[:max_chunks]):
                metadata = metadatas[i] if i < len(metadatas) else {}
                context.append({
                    'content': doc,
                    'title': metadata.get('title', ''),
                    'url': metadata.get('url', '')
                })
        return context
    except Exception as e:
        logger.error(f"Error processing context: {str(e)}")
        return []

def augment_query(query: str, context: List[Dict], conversation_history: List[Dict]) -> str:
    """Augment user query with context and conversation history."""
    formatted_context = "\n\n".join([
        f"Title: {ctx['title']}\nContent: {ctx['content']}\nSource: {ctx['url']}"
        for ctx in context
    ])
    
    # Format conversation history
    conversation_context = ""
    if conversation_history:
        conversation_context = "\nPrevious conversation:\n" + "\n".join([
            f"User: {msg['content']}" if msg['role'] == 'user' 
            else f"Assistant: {msg['content']}"
            for msg in conversation_history[-4:]  # Include last 2 exchanges (4 messages)
        ])
    
    return f"""Context from website: {formatted_context}
        {conversation_context}
        
        Current query: {query}"""

async def update_chroma_index(
    collection,
    chunked_posts: List[Dict],
    batch_size: int = 100
) -> None:
    """Update ChromaDB index with new chunks."""
    try:
        for post in chunked_posts:
            embeddings = []
            documents = []
            ids = []
            metadatas = []
            
            for i, chunk in enumerate(post['chunks']):
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
        
        logger.info(f"Successfully updated ChromaDB index with {len(chunked_posts)} posts")
    except Exception as e:
        logger.error(f"Error updating ChromaDB index: {str(e)}")
        raise
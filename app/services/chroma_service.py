import chromadb
from chromadb.config import Settings
import re
from config import settings
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

class ChromaService:
    def __init__(self):
        try:
            self.client = chromadb.Client(Settings(
                persist_directory=settings.CHROMA_PERSIST_DIRECTORY,
                is_persistent=True
            ))
            logger.info("ChromaDB client initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing ChromaDB client: {str(e)}")
            raise

    def _sanitize_collection_name(self, name: str) -> str:
        """Sanitize the collection name to meet ChromaDB requirements."""
        # Replace spaces with underscores and any non-alphanumeric chars (except - and _)
        sanitized = re.sub(r'[^\w\-]', '_', name)
        # Ensure it starts with a letter or number
        if not sanitized[0].isalnum():
            sanitized = 'user' + sanitized
        # Ensure it's within length limits
        if len(sanitized) < 3:
            sanitized = sanitized + '_collection'
        if len(sanitized) > 63:
            sanitized = sanitized[:63]
        # Ensure it ends with an alphanumeric character
        if not sanitized[-1].isalnum():
            sanitized = sanitized + '0'
        return sanitized

    def get_or_create_collection(self, user_id: str):
        """Get or create a ChromaDB collection for a user."""
        try:
            collection_name = self._sanitize_collection_name(f"user_{user_id}")
            logger.info(f"Using collection name: {collection_name}")
            
            try:
                collection = self.client.get_collection(name=collection_name)
                logger.info(f"Retrieved existing collection for user {user_id}")
            except:
                collection = self.client.create_collection(name=collection_name)
                logger.info(f"Created new collection for user {user_id}")
            return collection
        except Exception as e:
            logger.error(f"Error with ChromaDB collection for user {user_id}: {str(e)}")
            raise

    async def add_documents(
        self,
        user_id: str,
        documents: List[Dict],
        embeddings: Optional[List[List[float]]] = None
    ):
        """Add documents to a user's collection."""
        try:
            collection = self.get_or_create_collection(user_id)
            ids = [f"doc_{idx}" for idx in range(len(documents))]
            metadatas = [{
                'title': doc.get('title', ''),
                'url': doc.get('url', ''),
                'post_id': doc.get('post_id', '')
            } for doc in documents]

            collection.add(
                documents=[doc['content'] for doc in documents],
                embeddings=embeddings,
                metadatas=metadatas,
                ids=ids
            )
            logger.info(f"Added {len(documents)} documents to collection for user {user_id}")
        except Exception as e:
            logger.error(f"Error adding documents to ChromaDB: {str(e)}")
            raise

    async def query_documents(
        self,
        user_id: str,
        query_texts: List[str],
        n_results: int = 3
    ):
        """Query documents in a user's collection."""
        try:
            collection = self.get_or_create_collection(user_id)
            results = collection.query(
                query_texts=query_texts,
                n_results=n_results,
                include_metadata=True
            )
            return results
        except Exception as e:
            logger.error(f"Error querying ChromaDB: {str(e)}")
            raise

    async def delete_collection(self, user_id: str):
        """Delete a user's entire collection."""
        try:
            collection_name = self._sanitize_collection_name(f"user_{user_id}")
            self.client.delete_collection(name=collection_name)
            logger.info(f"Deleted collection for user {user_id}")
        except Exception as e:
            logger.error(f"Error deleting ChromaDB collection: {str(e)}")
            raise
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse
from typing import Dict, List
import uuid
import logging
from ..models.schemas import UserConfig, WebsiteUpdate, ChatQuery, ChatResponse
from ..services.auth import verify_token
from ..services.chroma_service import ChromaService
from ..services.claude_service import ClaudeService
from ..services.s3_service import S3Service
from ..utils.helpers import (
    fetch_wordpress_posts,
    chunk_posts,
    embed_query,
    posts_are_equal,
    similarity_search,
    get_context,
    augment_query,
    update_chroma_index
)

router = APIRouter()
logger = logging.getLogger(__name__)

conversations = {} # Store conversation history

# Initialize services
chroma_service = ChromaService()
s3_service = S3Service()

@router.post("/initialize")
async def initialize_user(
    config: UserConfig,
    user_id: str = Depends(verify_token)
):
    """Initialize user's website data."""
    if config.user_id != user_id:
        raise HTTPException(status_code=403, detail="User ID mismatch")
    
    try:
        # Check existing data
        data_status = await s3_service.check_user_data_exists(user_id)
        logger.info(f"Current data status for user {user_id}: {data_status}")

        # Fetch all posts
        logger.info(f"Fetching posts from {config.wp_posts_url}")
        latest_posts = fetch_wordpress_posts(config.wp_posts_url)
        
        if not latest_posts:
            raise HTTPException(status_code=500, detail="No posts were fetched")
        
        logger.info(f"Fetched {len(latest_posts)} posts")

        # Check if this is a new user
        if not data_status['posts']:
            logger.info("New user - processing all posts")
            
            # Process posts into chunks
            logger.info("Creating chunks from posts")
            chunked_posts = chunk_posts(latest_posts)
            
            # Save to S3
            logger.info("Saving initial data to S3")
            await s3_service.save_data(user_id, latest_posts, "posts")
            await s3_service.save_data(user_id, chunked_posts, "chunked_posts")
            
            # Create and update ChromaDB
            logger.info("Creating ChromaDB collection and adding documents")
            collection = chroma_service.get_or_create_collection(user_id)
            await update_chroma_index(collection, chunked_posts)
            
            return {
                "status": "success",
                "message": "Successfully initialized new user",
                "details": {
                    "total_posts": len(latest_posts),
                    "total_chunks": len(chunked_posts)
                }
            }
        
        # Existing user - check for updates
        existing_posts = await s3_service.load_data(user_id, "posts")
        new_posts = [
            post for post in latest_posts
            if not any(posts_are_equal(post, cached_post) 
                      for cached_post in existing_posts)
        ]
        
        if not new_posts:
            return {
                "status": "success",
                "message": "No new content to process",
                "details": {
                    "total_posts": len(existing_posts),
                    "new_posts": 0
                }
            }
        
        # Process new posts
        logger.info(f"Processing {len(new_posts)} new posts")
        new_chunked_posts = chunk_posts(new_posts)
        
        # Update existing data
        all_posts = existing_posts + new_posts
        existing_chunks = await s3_service.load_data(user_id, "chunked_posts") or []
        all_chunks = existing_chunks + new_chunked_posts
        
        # Save updates to S3
        await s3_service.save_data(user_id, all_posts, "posts")
        await s3_service.save_data(user_id, all_chunks, "chunked_posts")
        
        # Update ChromaDB
        collection = chroma_service.get_or_create_collection(user_id)
        await update_chroma_index(collection, new_chunked_posts)
        
        return {
            "status": "success",
            "message": "Successfully updated existing user",
            "details": {
                "total_posts": len(all_posts),
                "new_posts": len(new_posts),
                "total_chunks": len(all_chunks),
                "new_chunks": len(new_chunked_posts)
            }
        }

    except Exception as e:
        logger.error(f"Error during initialization: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/query")
async def process_query(
    query: ChatQuery,
    user_id: str = Depends(verify_token)
):
    """Process a chat query using RAG with augmented context."""
    if query.user_id != user_id:
        raise HTTPException(status_code=403, detail="User ID mismatch")
    
    try:
        conversation_id = query.conversation_id or str(uuid.uuid4())

        if conversation_id not in conversations:
            conversations[conversation_id] = []

        data_status = await s3_service.check_user_data_exists(user_id)
        if not data_status['chunked_posts']:
            raise HTTPException(
                status_code=400,
                detail="No content found for this user. Please initialize first."
            )

        # Load chunked posts
        chunked_posts = await s3_service.load_data(user_id, "chunked_posts")
        if not chunked_posts:
            raise HTTPException(
                status_code=404,
                detail="Failed to load user content"
            )

        # Get relevant context
        collection = chroma_service.get_or_create_collection(user_id)
        query_embedding = embed_query(query.query)
        search_results = similarity_search(query_embedding, collection)
        context = get_context(search_results)

        # Augment the query with context and conversation history
        augmented_query = augment_query(
            query=query.query,
            context=context,
            conversation_history=conversations.get(conversation_id, [])
        )

        # Response using augmented query
        claude_service = ClaudeService(query.claude_api_key)
        response = await claude_service.generate_response(
            query=augmented_query,  # Use augmented query instead of raw query
            context=context,
            chat_history=conversations[conversation_id]
        )

        # Store the interaction in conversation history
        conversations[conversation_id].append({
            "role": "user",
            "content": query.query  # Store original query in history
        })
        conversations[conversation_id].append({
            "role": "assistant",
            "content": response
        })

        if len(conversations) > 1000:  # Limit total conversations
            oldest_id = min(conversations.keys())
            del conversations[oldest_id]

        return ChatResponse(
            response=response,
            conversation_id=conversation_id
        )

    except Exception as e:
        logger.error(f"Error processing query: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/update")
async def update_content(
    update: WebsiteUpdate,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(verify_token)
):
    """Update user's website content in background."""
    if update.user_id != user_id:
        raise HTTPException(status_code=403, detail="User ID mismatch")

    async def background_update(user_id: str, wp_posts_url: str):
        try:
            # Verify user data exists
            data_status = await s3_service.check_user_data_exists(user_id)
            if not data_status['posts']:
                logger.error(f"No existing data found for user {user_id}")
                return

            # Fetch latest posts
            logger.info(f"Fetching latest posts for user {user_id}")
            latest_posts = fetch_wordpress_posts(wp_posts_url)
            if not latest_posts:
                logger.error("No posts were fetched")
                return

            # Load existing posts
            existing_posts = await s3_service.load_data(user_id, "posts")

            # Find new posts
            new_posts = [
                post for post in latest_posts
                if not any(posts_are_equal(post, cached_post) 
                          for cached_post in existing_posts)
            ]

            if new_posts:
                logger.info(f"Found {len(new_posts)} new posts")
                
                # Update posts
                all_posts = existing_posts + new_posts
                await s3_service.save_data(user_id, all_posts, "posts")

                # Update chunks
                new_chunked_posts = chunk_posts(new_posts)
                existing_chunks = await s3_service.load_data(user_id, "chunked_posts")
                all_chunks = existing_chunks + new_chunked_posts
                await s3_service.save_data(user_id, all_chunks, "chunked_posts")

                # Update ChromaDB
                collection = chroma_service.get_or_create_collection(user_id)
                await update_chroma_index(collection, new_chunked_posts)

                logger.info(f"Successfully updated content for user {user_id}")
            else:
                logger.info(f"No new posts found for user {user_id}")

        except Exception as e:
            logger.error(f"Error in background update for user {user_id}: {str(e)}")

    background_tasks.add_task(background_update, user_id, str(update.wp_posts_url))
    return {
        "status": "success",
        "message": "Content update initiated in background"
    }

@router.delete("/user/{user_id}")
async def delete_user_data(
    user_id: str,
    current_user: str = Depends(verify_token)
):
    """Delete all data for a user from both S3 and ChromaDB."""
    # Verify user is deleting their own data
    if user_id != current_user:
        raise HTTPException(
            status_code=403,
            detail="Not authorized to delete other user's data"
        )
    
    try:
        # Check if user data exists
        data_status = await s3_service.check_user_data_exists(user_id)
        if not data_status['posts'] and not data_status['chunked_posts']:
            return {
                "status": "success",
                "message": "No data found for user"
            }

        # Delete from S3
        logger.info(f"Deleting S3 data for user {user_id}")
        await s3_service.delete_user_data(user_id)

        # Delete from ChromaDB
        logger.info(f"Deleting ChromaDB collection for user {user_id}")
        await chroma_service.delete_collection(user_id)

        return {
            "status": "success",
            "message": "Successfully deleted all user data",
            "details": {
                "s3_data_deleted": True,
                "chroma_collection_deleted": True
            }
        }

    except Exception as e:
        logger.error(f"Error deleting user data: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete user data: {str(e)}"
        )
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, List
import uuid
import logging

from ..models.schemas import (
    UserRegistration, 
    UserResponse, 
    WebsiteUpdate, 
    ChatQuery, 
    ChatResponse
)
from ..models.database import get_db
from ..services.auth import verify_token, create_access_token
from ..services.user_service import UserService
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

# Initialize services
chroma_service = ChromaService()
s3_service = S3Service()

# Store conversation history
conversations = {}

@router.post("/register", response_model=UserResponse)
async def register_user(
    user_data: UserRegistration,
    db: AsyncSession = Depends(get_db)
):
    """Register a new user, initialize content, and return their unique ID with access token."""
    try:
        # Create user
        user_service = UserService(db)
        user = await user_service.create_user(user_data)
        
        # Generate access token
        token = create_access_token({
            "sub": user.id,
            "email": user.email
        })

        try:
            # Fetch all posts
            logger.info(f"Fetching posts from {user.wp_posts_url}")
            latest_posts = fetch_wordpress_posts(user.wp_posts_url)
            
            if not latest_posts:
                raise HTTPException(status_code=500, detail="No posts were fetched")
            
            logger.info(f"Fetched {len(latest_posts)} posts")
            
            # Process posts into chunks
            logger.info("Creating chunks from posts")
            chunked_posts = chunk_posts(latest_posts)
            
            # Save to S3
            logger.info("Saving initial data to S3")
            await s3_service.save_data(user.id, latest_posts, "posts")
            await s3_service.save_data(user.id, chunked_posts, "chunked_posts")
            
            # Create and update ChromaDB
            logger.info("Creating ChromaDB collection and adding documents")
            collection = chroma_service.get_or_create_collection(user.id)
            await update_chroma_index(collection, chunked_posts)
            
            logger.info("Content initialization completed successfully")

        except Exception as e:
            logger.error(f"Error during content initialization: {str(e)}")
            # If initialization fails, delete the user and raise error
            await user_service.delete_user(user.id)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to initialize content: {str(e)}"
            )
        
        return UserResponse(
            user_id=user.id,
            name=user.name,
            email=user.email,
            wp_posts_url=user.wp_posts_url,
            created_at=user.created_at,
            access_token=token
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/query", response_model=ChatResponse)
async def process_query(
    query: ChatQuery,
    user_id: str = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """Process a chat query using RAG with augmented context."""
    try:
        # Verify user exists
        user_service = UserService(db)
        user = await user_service.get_user_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        if query.user_id != user_id:
            raise HTTPException(status_code=403, detail="User ID mismatch")

        conversation_id = query.conversation_id or str(uuid.uuid4())
        logger.info(f"Processing query for user {user_id}, conversation {conversation_id}")

        if conversation_id not in conversations:
            conversations[conversation_id] = []

        # Check S3 data
        data_status = await s3_service.check_user_data_exists(user_id)
        logger.info(f"S3 data status: {data_status}")
        
        if not data_status['chunked_posts']:
            raise HTTPException(
                status_code=400,
                detail="No content found for this user. Please initialize first."
            )

        # Load chunked posts and verify content
        chunked_posts = await s3_service.load_data(user_id, "chunked_posts")
        logger.info(f"Loaded {len(chunked_posts) if chunked_posts else 0} chunked posts")
        
        if not chunked_posts:
            raise HTTPException(
                status_code=404,
                detail="Failed to load user content"
            )

        # Get ChromaDB collection and verify
        collection = chroma_service.get_or_create_collection(user_id)
        logger.info(f"Retrieved ChromaDB collection for user {user_id}")

        # Generate query embedding
        query_embedding = embed_query(query.query)
        logger.info("Generated query embedding")

        # Perform similarity search
        search_results = similarity_search(query_embedding, collection)
        logger.info(f"Similarity search results: {search_results}")

        # Get and verify context
        context = get_context(search_results)
        logger.info(f"Retrieved context: {context}")

        if not context:
            logger.warning("No relevant context found for query")
            context = [{"content": "No specific content found for this query.", "title": "", "url": ""}]

        # Augment query
        augmented_query = augment_query(
            query=query.query,
            context=context,
            conversation_history=conversations.get(conversation_id, [])
        )
        logger.info("Query augmented with context and history")

        # Generate response
        claude_service = ClaudeService(user.claude_api_key)
        response = await claude_service.generate_response(
            query=augmented_query,
            context=context,
            chat_history=conversations[conversation_id]
        )
        logger.info("Generated response from Claude")

        # Update conversation history
        conversations[conversation_id].append({
            "role": "user",
            "content": query.query
        })
        conversations[conversation_id].append({
            "role": "assistant",
            "content": response
        })

        # Manage conversation history size
        if len(conversations) > 1000:
            oldest_id = min(conversations.keys())
            del conversations[oldest_id]

        return ChatResponse(
            response=response,
            conversation_id=conversation_id
        )

    except Exception as e:
        logger.error(f"Error processing query: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/update")
async def update_content(
    update: WebsiteUpdate,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """Update user's website content in background."""
    try:
        # Verify user exists
        user_service = UserService(db)
        user = await user_service.get_user_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if update.user_id != user_id:
            raise HTTPException(status_code=403, detail="User ID mismatch")

        # Update WordPress URL if changed
        if str(update.wp_posts_url) != user.wp_posts_url:
            await user_service.update_user(user_id, str(update.wp_posts_url))

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

        background_tasks.add_task(
            background_update,
            user_id,
            str(update.wp_posts_url)
        )

        return {
            "status": "success",
            "message": "Content update initiated in background"
        }

    except Exception as e:
        logger.error(f"Error updating content: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/user/{user_id}")
async def delete_user_data(
    user_id: str,
    current_user: str = Depends(verify_token),
    db: AsyncSession = Depends(get_db)
):
    """Delete all user data from PostgreSQL, S3, and ChromaDB."""
    if user_id != current_user:
        raise HTTPException(
            status_code=403,
            detail="Not authorized to delete other user's data"
        )
    
    try:
        # Delete from PostgreSQL
        user_service = UserService(db)
        user_deleted = await user_service.delete_user(user_id)
        if not user_deleted:
            raise HTTPException(status_code=404, detail="User not found")

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
                "user_deleted": True,
                "s3_data_deleted": True,
                "chroma_collection_deleted": True
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting user data: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete user data: {str(e)}"
        )
from typing import AsyncGenerator
from fastapi import Depends, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession
from ..models.database import get_db
from ..services.user_service import UserService
from ..services.chroma_service import ChromaService
from ..services.s3_service import S3Service

async def get_user_service(db: AsyncSession = Depends(get_db)) -> UserService:
    return UserService(db)

async def get_chroma_service() -> ChromaService:
    return ChromaService()

async def get_s3_service() -> S3Service:
    return S3Service()

async def verify_content_type(
    content_type: str = Header(..., description="The content type of the request")
) -> str:
    if content_type != "application/json":
        raise HTTPException(
            status_code=400,
            detail="Content Type must be application/json"
        )
    return content_type

async def rate_limit_check(
    x_api_key: str = Header(..., description="API key for rate limiting")
) -> None:
    # Rate limiting logic will do it later. 
    pass
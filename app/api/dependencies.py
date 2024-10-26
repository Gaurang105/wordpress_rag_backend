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

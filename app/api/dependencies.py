from typing import Dict
from fastapi import Header, HTTPException
from ..services.chroma_service import ChromaService
from ..services.s3_service import S3Service

async def get_chroma_service() -> ChromaService:
    """Dependency to get ChromaDB service instance."""
    return ChromaService()

async def get_s3_service() -> S3Service:
    """Dependency to get S3 service instance."""
    return S3Service()

async def verify_content_type(
    content_type: str = Header(..., description="The content type of the request")
) -> str:
    """Verify that the content type is application/json."""
    if content_type != "application/json":
        raise HTTPException(
            status_code=400,
            detail="Content Type must be application/json"
        )
    return content_type

async def rate_limit_check(
    x_api_key: str = Header(..., description="API key for rate limiting")
) -> None:
    """Basic rate limiting check."""
    # Not needed now but for future
    pass
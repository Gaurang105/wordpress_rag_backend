from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader
from config import settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)

def create_access_token(user_id: str) -> str:
    """Create a new JWT token for a user."""
    expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {"sub": user_id, "exp": expire}
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def verify_token(token: str = Security(api_key_header)) -> str:
    """Verify a JWT token and return the user_id."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid authentication token")
        return user_id
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid authentication token")
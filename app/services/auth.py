from datetime import datetime, timedelta
from typing import Dict
from jose import JWTError, jwt
from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader
from ..models.schemas import TokenData
from config import settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)

def create_access_token(data: Dict) -> str:
    """Create a new JWT token."""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def verify_token(token: str = Security(api_key_header)) -> str:
    """Verify a JWT token and return the user_id."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")
        email: str = payload.get("email")
        
        if user_id is None or email is None:
            raise HTTPException(status_code=401, detail="Invalid authentication token")
        
        token_data = TokenData(user_id=user_id, email=email)
        return token_data.user_id
        
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid authentication token")
from pydantic import BaseModel, AnyHttpUrl, EmailStr
from typing import Optional
from datetime import datetime

class UserRegistration(BaseModel):
    name: str
    email: EmailStr
    claude_api_key: str
    wp_posts_url: AnyHttpUrl

class UserResponse(BaseModel):
    user_id: str
    name: str
    email: EmailStr
    wp_posts_url: AnyHttpUrl
    created_at: datetime
    access_token: Optional[str] = None

class WebsiteUpdate(BaseModel):
    user_id: str
    wp_posts_url: AnyHttpUrl

class ChatQuery(BaseModel):
    user_id: str
    query: str
    conversation_id: Optional[str] = None

class ChatResponse(BaseModel):
    response: str
    conversation_id: str

class TokenData(BaseModel):
    user_id: str
    email: str
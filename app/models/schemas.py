from pydantic import BaseModel, AnyHttpUrl, EmailStr, Field
from typing import List, Optional, Dict
from datetime import datetime

class UserRegistration(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    claude_api_key: str
    wp_posts_url: AnyHttpUrl

class UserInit(BaseModel):
    email: EmailStr
    claude_api_key: str
    wp_posts_url: AnyHttpUrl

class UserBase(BaseModel):
    user_id: str
    name: str
    email: EmailStr
    wp_posts_url: AnyHttpUrl

class UserResponse(UserBase):
    created_at: datetime
    access_token: Optional[str] = None

    class Config:
        from_attributes = True

class WebsiteUpdate(BaseModel):
    user_id: str
    wp_posts_url: AnyHttpUrl

class ChatQuery(BaseModel):
    user_id: str
    query: str
    claude_api_key: str
    conversation_id: Optional[str] = None

class ChatResponse(BaseModel):
    response: str
    conversation_id: str

class TokenData(BaseModel):
    user_id: str
    email: str
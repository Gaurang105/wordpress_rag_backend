from pydantic import BaseModel, AnyHttpUrl, Field
from typing import List, Optional, Dict

class UserConfig(BaseModel):
    user_id: str
    claude_api_key: str
    wp_posts_url: AnyHttpUrl

class WebsiteUpdate(BaseModel):
    user_id: str
    wp_posts_url: AnyHttpUrl

class ChatQuery(BaseModel):
    user_id: str
    query: str
    claude_api_key: str
    chat_history: Optional[List[Dict[str, str]]] = Field(default_factory=list)
    conversation_id: Optional[str] = None

class ChatResponse(BaseModel):
    response: str
    conversation_id: str
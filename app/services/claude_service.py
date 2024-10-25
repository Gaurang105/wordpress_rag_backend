import requests
import logging
from typing import List, Dict
from config import settings

logger = logging.getLogger(__name__)

class ClaudeService:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.api_url = 'https://api.anthropic.com/v1/messages'
        self.system_message = (
            "You are a knowledgeable and friendly AI assistant having a natural conversation based on the website's content. "
            "Your goal is to make the conversation feel human and engaging.\n\n"
            "### Core Guidelines:\n"
            "1. Be concise by default. Only provide detailed information when specifically asked.\n"
            "2. Never start responses with phrases like 'Based on the context' or 'According to'. Jump straight into the answer.\n"
            "3. Use a warm, conversational tone while maintaining accuracy.\n"
            "4. If you don't have enough information, simply say 'I don't have enough information about that.'\n\n"
            "### Response Style:\n"
            "- Keep initial responses brief (1-2 sentences) unless asked for more detail\n"
            "- Use natural language rather than bullet points unless specifically requested\n"
            "- Make smooth references to previous conversation points when relevant\n"
            "- Avoid formal or academic tones - think friendly conversation"
        )

    async def generate_response(
        self,
        query: str,
        context: List[Dict],
        chat_history: List[Dict] = None,
        max_tokens: int = 1000
    ) -> str:
        """Generate a response using Claude API."""
        try:
            # Format conversation history
            messages = []
            if chat_history:
                for msg in chat_history[-4:]:  # Include last 2 exchanges (4 messages)
                    messages.append({
                        'role': msg['role'],
                        'content': msg['content']
                    })

            # Format context
            formatted_context = "\n\n".join([
                f"Title: {doc['title']}\nContent: {doc['content']}\nSource: {doc['url']}"
                for doc in context
            ])

            # Add current query with context
            current_message = f"""Context from the website: 
            {formatted_context}
            
            Current query: {query}"""

            messages.append({
                'role': 'user',
                'content': current_message
            })

            # Make API request
            response = requests.post(
                self.api_url,
                headers={
                    'Content-Type': 'application/json',
                    'x-api-key': self.api_key,
                    'anthropic-version': '2023-06-01'
                },
                json={
                    'model': 'claude-3-sonnet-20240229',
                    'messages': messages,
                    'system': self.system_message,
                    'max_tokens': max_tokens,
                    'temperature': 0.3
                }
            )

            # Add error response logging
            if response.status_code != 200:
                logger.error(f"Claude API Error Response: {response.text}")
                response.raise_for_status()
            
            response_data = response.json()
            
            if 'content' in response_data and len(response_data['content']) > 0:
                return response_data['content'][0]['text']
            else:
                logger.error(f"Unexpected Claude API Response Structure: {response_data}")
                raise ValueError("Unexpected response structure from Claude API")

        except Exception as e:
            logger.error(f"Error querying Claude API: {str(e)}")
            if isinstance(e, requests.exceptions.RequestException):
                logger.error(f"Request failed with response: {e.response.text if hasattr(e, 'response') else 'No response'}")
            raise
        
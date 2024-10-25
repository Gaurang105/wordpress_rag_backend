import requests
import logging
from typing import List, Dict
from config import settings

logger = logging.getLogger(__name__)

class ClaudeService:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.api_url = 'https://api.anthropic.com/v1/messages'
        self.system_message = """You are a knowledgeable and friendly AI assistant having a natural conversation based on the website's content. 
        Your goal is to make the conversation feel human and engaging.

        ### Core Guidelines:
        1. Be concise by default. Only provide detailed information when specifically asked.
        2. Never start responses with phrases like 'Based on the context' or 'According to'. Jump straight into the answer.
        3. Use a warm, conversational tone while maintaining accuracy.
        4. If you don't have enough information, simply say 'I don't have enough information about that.'

        ### Response Style:
        - Keep initial responses brief (1-2 sentences) unless asked for more detail
        - Use natural language rather than bullet points unless specifically requested
        - Make smooth references to previous conversation points when relevant
        - Avoid formal or academic tones - think friendly conversation"""

    async def generate_response(
        self,
        query: str,
        context: List[Dict],
        conversation_history: List[Dict],
        max_tokens: int = 1000
    ) -> str:
        """Generate a response using Claude API."""
        try:
            # Format messages
            messages = []
            if conversation_history:
                for msg in conversation_history[-4:]:
                    messages.append({
                        "role": msg["role"],
                        "content": msg["content"]
                    })

            # Add current query with context
            formatted_context = "\n\n".join([
                f"Title: {doc['title']}\nContent: {doc['content']}\nSource: {doc['url']}"
                for doc in context
            ])

            query_with_context = f"""Context from the website: 
            {formatted_context}
            
            Current query: {query}"""

            messages.append({
                "role": "user",
                "content": query_with_context
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
                    'system': self.system_message,
                    'messages': messages,
                    'max_tokens': max_tokens,
                    'temperature': 0.3
                }
            )
            response.raise_for_status()
            
            response_data = response.json()
            if 'content' in response_data and len(response_data['content']) > 0:
                return response_data['content'][0]['text']
            else:
                raise ValueError("Unexpected response structure from Claude API")

        except Exception as e:
            logger.error(f"Error querying Claude API: {str(e)}")
            raise
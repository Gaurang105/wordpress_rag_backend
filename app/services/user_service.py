from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from typing import Optional
import logging
from ..models.database import User
from ..models.schemas import UserRegistration
from datetime import datetime

logger = logging.getLogger(__name__)

class UserService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_user(self, user_data: UserRegistration) -> User:
        """Create a new user."""
        try:
            # Check if email already exists
            existing_user = await self.get_user_by_email(user_data.email)
            if existing_user:
                raise ValueError("Email already registered")

            # Create new user
            db_user = User(
                name=user_data.name,
                email=user_data.email,
                wp_posts_url=str(user_data.wp_posts_url),
                claude_api_key=user_data.claude_api_key
            )
            
            self.db.add(db_user)
            await self.db.commit()
            await self.db.refresh(db_user)
            
            return db_user

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error creating user: {str(e)}")
            raise

    async def get_user_by_email(self, email: str) -> Optional[User]:
        """Retrieve user by email."""
        try:
            query = select(User).where(User.email == email)
            result = await self.db.execute(query)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error retrieving user by email: {str(e)}")
            raise

    async def get_user_by_id(self, user_id: str) -> Optional[User]:
        """Retrieve user by ID."""
        try:
            query = select(User).where(User.id == user_id)
            result = await self.db.execute(query)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error retrieving user by ID: {str(e)}")
            raise

    async def update_user(self, user_id: str, wp_posts_url: str) -> Optional[User]:
        """Update user's WordPress URL."""
        try:
            stmt = (
                update(User)
                .where(User.id == user_id)
                .values(
                    wp_posts_url=wp_posts_url,
                    updated_at=datetime.utcnow()
                )
                .returning(User)
            )
            result = await self.db.execute(stmt)
            await self.db.commit()
            return result.scalar_one_or_none()
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error updating user: {str(e)}")
            raise

    async def delete_user(self, user_id: str) -> bool:
        """Delete a user."""
        try:
            user = await self.get_user_by_id(user_id)
            if user:
                await self.db.delete(user)
                await self.db.commit()
                return True
            return False
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error deleting user: {str(e)}")
            raise
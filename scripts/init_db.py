import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from app.models.database import Base
from config import settings

async def init_db():
    engine = create_async_engine(settings.DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(init_db())
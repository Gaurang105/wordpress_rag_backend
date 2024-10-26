import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    # API Settings
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "WordPress RAG Backend"
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    
    # AWS Settings
    AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
    AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
    S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
    
    # ChromaDB Settings
    CHROMA_PERSIST_DIRECTORY = os.getenv("CHROMA_PERSIST_DIRECTORY", "./chroma_data")
    
    # Authentication Settings
    SECRET_KEY = os.getenv("SECRET_KEY")
    ALGORITHM = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

    # Database Settings
    POSTGRES_USER = os.getenv("POSTGRES_USER", "gauranggujrati")
    POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "admin")
    POSTGRES_SERVER = os.getenv("POSTGRES_SERVER", "localhost")
    POSTGRES_PORT = os.getenv("POSTGRES_PORT", 5432)
    POSTGRES_DB = os.getenv("POSTGRES_DB", "rag_backend_testing")
    DATABASE_URL = f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_SERVER}:{POSTGRES_PORT}/{POSTGRES_DB}"

settings = Settings()
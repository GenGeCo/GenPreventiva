"""
GenPreventiva - Configuration
Configurazione centralizzata dell'applicazione
"""
import os
from pathlib import Path
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # App
    APP_NAME: str = "GenPreventiva"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    SECRET_KEY: str = "change-me-in-production"

    # Paths
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    STORAGE_PATH: Path = Path("/opt/genpreventiva/storage")
    CHROMADB_PATH: Path = Path("/opt/genpreventiva/chromadb")

    # Database PostgreSQL
    DATABASE_URL: str = "postgresql://genpreventiva:kaheipuvMNjguLNZ9kLI0LZaUOBHNMBHp15ba6ha@127.0.0.1:5432/genpreventiva_db"

    # Redis (opzionale, per cache)
    REDIS_URL: str = "redis://127.0.0.1:6379/1"

    # Google Gemini API
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"
    EMBEDDING_MODEL: str = "text-embedding-004"

    # ChromaDB
    CHROMA_COLLECTION_NAME: str = "cnc_drawings"

    # Upload settings
    MAX_UPLOAD_SIZE: int = 50 * 1024 * 1024  # 50MB
    ALLOWED_EXTENSIONS: list = [".pdf", ".png", ".jpg", ".jpeg"]

    # RAG settings
    TOP_K_SIMILAR: int = 3  # Numero di esempi simili da recuperare

    # JWT Auth
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_HOURS: int = 24

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

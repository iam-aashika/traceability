import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    APP_ENV: str = "development"
    APP_PORT: int = 8000
    DATABASE_URL: str = f"sqlite:///{BASE_DIR / 'ct200_system.db'}"
    GENERATIONS_STORAGE_DIR: str = str(BASE_DIR / "storage" / "generations")
    
    # LLM Settings
    LLM_PROVIDER: str = "mock"  # mock, gemini, groq
    GEMINI_API_KEY: str = ""
    GROQ_API_KEY: str = ""
    LLM_MODEL: str = "gemini-1.5-flash"
    MAX_RETRIES: int = 3
    REQUEST_TIMEOUT: int = 30
    
    # OCR Settings
    TESSERACT_CMD: str = ""
    
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()

# Ensure storage directory exists
Path(settings.GENERATIONS_STORAGE_DIR).mkdir(parents=True, exist_ok=True)

import os
from pathlib import Path
from typing import List, Union, Optional, Any
from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
import json

BASE_DIR = Path(__file__).resolve().parent.parent.parent

class Settings(BaseSettings):
    PROJECT_NAME: str = "Medical Speech Transcription API"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    
    # MongoDB Database Configuration
    MONGODB_URL: str = "mongodb+srv://padakitejas_db_user:LBY4id3EGea93pRj@cluster0.aborp1b.mongodb.net/?retryWrites=true&w=majority"
    MONGODB_DB_NAME: str = "medical_system"

    @field_validator("MONGODB_URL", mode="before")
    def assemble_mongodb_url(cls, v: Optional[str]) -> str:
        if v and v.strip():
            return v.strip()
        env_uri = os.getenv("MONGODB_URI") or os.getenv("MONGO_URI")
        if env_uri and env_uri.strip():
            return env_uri.strip()
        return "mongodb+srv://padakitejas_db_user:LBY4id3EGea93pRj@cluster0.aborp1b.mongodb.net/?retryWrites=true&w=majority"

    # Database (SQLite standard SQL relational storage or PostgreSQL fallback)
    DATABASE_URL: str = "sqlite:///./medical_system.db"

    @field_validator("DATABASE_URL", mode="before")
    def assemble_database_url(cls, v: str) -> str:
        if isinstance(v, str) and v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql://", 1)
        return v
    
    # Redis cache/blacklist
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # Security
    JWT_SECRET_KEY: str = "supersecretmedicalkeychangeinproductionsecure2026"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # Voice AI & Clinical Orchestrator Configuration
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-3.8-flash"
    SARVAM_API_KEY: Optional[str] = None
    VOICE_ACTION_TTL_SECONDS: int = 300
    DEFAULT_CLINICAL_LANGUAGE: str = "kn"

    # CORS Configuration
    CORS_ORIGINS: Union[str, List[str]] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "*"
    ]

    @field_validator("CORS_ORIGINS", mode="before")
    def assemble_cors_origins(cls, v: Any) -> Union[str, List[str]]:
        if isinstance(v, list):
            return [str(item).strip() for item in v if str(item).strip()]
        if isinstance(v, str):
            clean_v = v.strip()
            if not clean_v:
                return []
            if clean_v.startswith("[") and clean_v.endswith("]"):
                try:
                    parsed = json.loads(clean_v)
                    if isinstance(parsed, list):
                        return [str(item).strip() for item in parsed if str(item).strip()]
                except Exception:
                    clean_v = clean_v.strip("[]").replace("'", "").replace('"', "")
            return [i.strip() for i in clean_v.split(",") if i.strip()]
        return v

    @property
    def cors_origins_list(self) -> List[str]:
        if isinstance(self.CORS_ORIGINS, list):
            return self.CORS_ORIGINS
        if isinstance(self.CORS_ORIGINS, str):
            clean = self.CORS_ORIGINS.strip()
            if clean.startswith("[") and clean.endswith("]"):
                try:
                    parsed = json.loads(clean)
                    if isinstance(parsed, list):
                        return [str(i).strip() for i in parsed if str(i).strip()]
                except Exception:
                    clean = clean.strip("[]").replace("'", "").replace('"', "")
            return [i.strip() for i in clean.split(",") if i.strip()]
        return ["*"]

    model_config = SettingsConfigDict(
        env_file=[str(BASE_DIR / ".env"), ".env", "backend/.env"],
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )

settings = Settings()

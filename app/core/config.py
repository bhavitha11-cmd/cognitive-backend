import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # API Metadata
    PROJECT_NAME: str = "Cognitive ERP API"
    PROJECT_VERSION: str = "1.0.0"
    
    # Environment Settings
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    
    # Database Settings
    DATABASE_URL: str
    DB_ECHO: bool = False
    
    # Security Settings
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Frontend Settings
    FRONTEND_URL: str = "http://localhost:5173"

    # Pydantic Settings Configuration
    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )


# Expose global settings instance
settings = Settings()

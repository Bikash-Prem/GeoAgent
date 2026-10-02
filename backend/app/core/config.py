from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    database_url: str = "sqlite:///./geoagentic.db"
    cors_origins: str = "http://localhost:5173"
    allowed_hosts: str = "localhost,127.0.0.1"
    api_key: str = ""
    environment: str = "development"
    enable_demo_stream: bool = True
    docs_enabled: bool = True
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_ENV = Path(__file__).resolve().parents[3] / ".env"

class Settings(BaseSettings):
    database_url: str = "sqlite:///./geoagentic.db"
    cors_origins: str = "http://localhost:5173"
    allowed_hosts: str = "localhost,127.0.0.1"
    api_key: str = ""
    environment: str = "development"
    enable_demo_stream: bool = True
    docs_enabled: bool = True
    routing_provider: str = "google"
    google_routes_api_key: str = ""
    google_routing_preference: str = "TRAFFIC_AWARE"
    destination_lat: float = 19.0509
    destination_lon: float = 72.8296
    mapbox_access_token: str = ""
    traffic_provider: str = "local"
    tomtom_api_key: str = ""
    fleet_provider: str = "local"
    fleet_api_url: str = ""
    fleet_api_username: str = ""
    fleet_api_password: str = ""
    provider_timeout_seconds: float = 5.0
    twin_tick_hz: float = 0.2
    model_config = SettingsConfigDict(env_file=(str(ROOT_ENV), ".env"), extra="ignore")

settings = Settings()

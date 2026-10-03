from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    database_url: str = "sqlite:///./geoagentic.db"
    cors_origins: str = "http://localhost:5173"
    allowed_hosts: str = "localhost,127.0.0.1"
    api_key: str = ""
    environment: str = "development"
    enable_demo_stream: bool = True
    docs_enabled: bool = True
    response_target_min: float = 15.0   # operator-set target: hospital ETA (upper bound) above this triggers a backup hedge
    coverage_target_min: float = 10.0   # a demand point counts as covered if an available unit can reach it within this
    # ── external providers (all optional; without credentials the platform runs on its built-in sources) ──
    routing_provider: str = "google"        # google | mapbox  (used only when its key is set)
    google_routes_api_key: str = ""
    google_routing_preference: str = "TRAFFIC_AWARE"
    mapbox_access_token: str = ""
    traffic_provider: str = "local"         # local | tomtom
    tomtom_api_key: str = ""
    fleet_provider: str = "local"           # local | traccar
    fleet_api_url: str = ""
    fleet_api_username: str = ""
    fleet_api_password: str = ""
    traccar_device_map: str = ""            # "12:AMB-07,15:AMB-12"
    provider_timeout_seconds: float = 5.0
    destination_lat: float = 12.9720        # default destination when a unit has no hospital set
    destination_lon: float = 77.6070
    twin_tick_hz: float = 0.2               # control-loop rate (0.2 = every 5 s)
    incident_sync_seconds: float = 60.0
    anthropic_api_key: str = ""         # optional: lets GeoAgent phrase answers with an LLM (numbers are verified)
    llm_model: str = "claude-sonnet-5-5"
    model_config = SettingsConfigDict(env_file="../.env", extra="ignore")

settings = Settings()

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "RoadMate AI"
    environment: str = "local"
    google_maps_api_key: str | None = None
    gemini_api_key: str | None = None
    spotify_access_token: str | None = None
    pubsub_project_id: str | None = None
    pubsub_topic: str = "roadmate-events"
    event_log_path: str = "artifacts/events.jsonl"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()

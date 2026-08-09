from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Road Friend"
    environment: str = "local"

    # Public information / AI
    google_maps_api_key: str | None = None
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.6-flash"

    # Personal integrations
    spotify_access_token: str | None = None
    gmail_credentials_path: str = "credentials.json"
    gmail_token_path: str = "token.json"
    allow_macos_messages: bool = False

    # Data platform
    pubsub_project_id: str | None = None
    pubsub_topic: str = "roadmate-events"
    event_log_path: str = "artifacts/events.jsonl"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()

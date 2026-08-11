from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application configuration loaded from environment variables.
    """

    google_api_key: str
    gemini_model: str = "gemini-3.5-flash"
    temperature: float = 0.2
    max_retries: int = 3

    log_level: str = "INFO"


    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


settings = Settings()

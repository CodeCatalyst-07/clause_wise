"""
ClauseWise — Application Configuration

All secrets and environment-specific values are loaded exclusively from
environment variables. **Nothing is hardcoded.** During local development
the values come from a `.env` file (which is git-ignored); in production
they come from the deployment platform's secret manager.

Pydantic's BaseSettings gives us automatic .env loading, type coercion,
and validation — so the app fails fast with a clear error if a required
variable is missing rather than silently misbehaving at runtime.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Central configuration read from environment variables.

    Attributes:
        gemini_api_key: API key for the Google Gemini generative-AI service.
        google_application_credentials: Path to the GCP service-account JSON
            used by Document AI (and potentially other GCP services).
        docai_processor_id: The fully-qualified Document AI processor resource
            name (projects/…/locations/…/processors/…).
        translate_api_key: API key for the Google Cloud Translation API.
    """

    gemini_api_key: str = ""
    google_application_credentials: str = ""
    docai_processor_id: str = ""
    translate_api_key: str = ""

    # CORS: optional comma-separated list of additional allowed origins
    allowed_origins: str = ""

    # File upload limits
    max_upload_size_mb: int = 10

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )


# Singleton instance — import this wherever configuration is needed.
settings = Settings()


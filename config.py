"""
Configuration management for Cloud-Synced Personal Reader (READ_V2).
Loads settings from environment variables and .env file using Pydantic Settings.
"""

from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings and cloud environment variables."""
    
    # GCP Infrastructure Settings
    gcp_project_id: str = Field(default="personal-reader-app", description="GCP Project ID")
    gcp_region: str = Field(default="us-central1", description="Pinned GCP Region (us-central1)")
    gcs_bucket_name: str = Field(default="my-reader-library-us-central1", description="GCS Bucket Name")
    
    # Authentication & Security
    google_client_id: str = Field(default="mock-client-id.apps.googleusercontent.com", description="OAuth 2.0 Web Client ID")
    allowed_email: str = Field(default="reader-owner@gmail.com", description="Authorized Single-User Email")
    
    # Development & Offline Mode
    dev_mode: bool = Field(default=True, description="Enable local developer features")
    mock_gcp: bool = Field(default=True, description="Mock Firestore & GCS for local testing when cloud is not connected")
    
    # Server Binding
    host: str = Field(default="127.0.0.1", description="Server bind host")
    port: int = Field(default=8000, description="Server bind port")
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )


@lru_cache
def get_settings() -> Settings:
    """Returns cached application settings instance."""
    return Settings()


if __name__ == "__main__":
    print("--- Running config.py Self-Test ---")
    settings = get_settings()
    print(f"GCP Project ID  : {settings.gcp_project_id}")
    print(f"GCP Region      : {settings.gcp_region}")
    print(f"GCS Bucket      : {settings.gcs_bucket_name}")
    print(f"Allowed Email   : {settings.allowed_email}")
    print(f"Dev Mode        : {settings.dev_mode}")
    print(f"Mock GCP        : {settings.mock_gcp}")
    print(f"Host / Port     : {settings.host}:{settings.port}")
    
    assert settings.gcp_region in ("us-central1", "us-east1"), "Region MUST be us-central1 or us-east1 for Always-Free tier!"
    print("\n[OK] Configuration self-test passed successfully!")


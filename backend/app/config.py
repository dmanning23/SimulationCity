from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    secret_key: str = "change-me-in-production-use-a-long-random-string"
    environment: str = "development"

    # MongoDB
    mongodb_url: str = "mongodb://localhost:27017"
    mongodb_db_name: str = "simulationcity"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # JWT
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24  # 24 hours

    # Feature flags
    enable_sd_generation: bool = False

    # AWS S3 (premium)
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_s3_bucket: str = "simulationcity-assets"
    aws_region: str = "us-east-1"

    # Replicate (premium)
    replicate_api_token: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

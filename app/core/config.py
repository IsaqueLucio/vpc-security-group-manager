from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    secret_key: str = Field(min_length=32)
    algorithm: str = "HS256"
    database_url: str = (
        "postgresql+psycopg://vpc_manager:local-development-only"
        "@localhost:5432/vpc_manager"
    )
    access_token_expire_minutes: int = Field(default=30, gt=0)
    vpc_limit_per_owner: int = Field(default=5, gt=0)
    vpc_provisioning_delay_seconds: float = Field(default=30, ge=0)
    database_lock_timeout_ms: int = Field(default=5000, gt=0)
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://localhost:5173"]
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()

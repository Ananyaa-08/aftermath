from typing import Literal, Self

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AFTERMATH_", env_file=".env", extra="forbid", hide_input_in_errors=True
    )
    environment: Literal["development", "test", "production"] = "development"
    database_url: SecretStr
    cors_origins: list[str] = ["http://localhost:3000"]

    @model_validator(mode="after")
    def validate_database(self) -> Self:
        try:
            url = make_url(self.database_url.get_secret_value())
            if url.drivername != "postgresql+psycopg" or not url.host or not url.database:
                raise ValueError
        except Exception:
            raise ValueError("A PostgreSQL psycopg connection URL is required") from None
        if "*" in self.cors_origins:
            raise ValueError("CORS origins must be explicit")
        if self.environment == "production" and any(
            "localhost" in origin or "127.0.0.1" in origin for origin in self.cors_origins
        ):
            raise ValueError("Production requires explicit deployed CORS origins")
        return self

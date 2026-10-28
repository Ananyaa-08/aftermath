from pathlib import Path
from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AFTERMATH_", env_file=".env", extra="forbid", hide_input_in_errors=True
    )
    environment: Literal["development", "test", "production"] = "development"
    database_url: SecretStr
    dev_identity: str | None = None
    data_dir: Path = Field(default_factory=lambda: Path.home() / ".local/share/aftermath/objects")
    max_body_bytes: int = Field(default=1048576, ge=1024, le=16777216)
    max_source_bytes: int = Field(default=262144, ge=1, le=1048576)
    max_corpus_versions: int = Field(default=2000, ge=1, le=10000)
    max_documents_per_delivery: int = Field(default=32, ge=1, le=32)
    max_passages_per_document: int = Field(default=500, ge=1, le=5000)
    max_passage_length: int = Field(default=100000, ge=1200, le=1000000)
    max_alignment_candidate_pairs: int = Field(default=20000, ge=1, le=1000000)
    max_timeline_breakpoints: int = Field(default=1000, ge=1, le=10000)
    max_returned_spans: int = Field(default=100, ge=1, le=500)
    cors_origins: list[str] = ["http://localhost:3000"]
    gemini_api_key: SecretStr | None = None
    force_fallback: bool = False

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
        if self.environment == "production" and self.dev_identity is not None:
            raise ValueError("Development identity bypass is forbidden in production")
        if self.dev_identity is not None and not self.dev_identity.strip():
            raise ValueError("Development identity must be nonempty")
        if self.gemini_api_key is not None and not self.gemini_api_key.get_secret_value().strip():
            self.gemini_api_key = None
        return self

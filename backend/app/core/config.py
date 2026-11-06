from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SQSP_", env_file=".env", extra="ignore")
    database_url: str = "sqlite:///./data/sqsp.db"
    redis_url: str = "redis://localhost:6379/0"
    queue_backend: Literal["redis", "database"] = "database"
    artifact_root: Path = Path("data/artifacts")
    rules_path: Path = ROOT / "rules/builtin-rules.yaml"
    policy_path: Path = ROOT / "rules/policy.yaml"
    max_upload_bytes: int = Field(default=20 * 1024 * 1024, gt=0)
    max_expanded_bytes: int = Field(default=100 * 1024 * 1024, gt=0)
    max_file_bytes: int = Field(default=10 * 1024 * 1024, gt=0)
    max_entries: int = Field(default=300, gt=0, le=10000)
    max_depth: int = Field(default=10, gt=0, le=64)
    max_compression_ratio: int = Field(default=100, gt=0)
    worker_lease_seconds: int = Field(default=600, ge=30)
    max_scan_attempts: int = Field(default=2, ge=1, le=5)

    @model_validator(mode="after")
    def validate_limits(self):
        if self.max_file_bytes > self.max_expanded_bytes:
            raise ValueError("max_file_bytes must not exceed max_expanded_bytes")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()

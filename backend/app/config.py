"""Application configuration loaded from environment / .env."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent
DEFAULT_DATA_DIR = REPO_ROOT / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"), env_file_encoding="utf-8", extra="ignore",
    )
    app_name: str = "SOC Workbench"
    environment: str = "development"
    debug: bool = True
    admin_username: str = "admin"
    admin_password: str = "changeme"
    secret_key: str = "dev-insecure-secret-change-me"
    access_token_expire_minutes: int = 60 * 24 * 7
    default_tenant_id: str = "default"
    admin_role: str = "admin"
    data_dir: Path = DEFAULT_DATA_DIR
    database_url: str = ""
    cors_origins: str = "http://localhost:5173,http://localhost:3000"
    anthropic_api_key: str = ""
    default_llm_model: str = "sorin-opus-4-8"
    llm_max_tokens: int = 4096
    llm_timeout: int = 120
    compatible_base_url: str = ""
    compatible_api_key: str = ""
    atlassian_oauth_client_id: str = ""
    atlassian_oauth_client_secret: str = ""
    atlassian_oauth_redirect_uri: str = "http://localhost:8000/api/atlassian/oauth/callback"
    atlassian_bulk_max_issues: int = 100
    atlassian_history_retention_days: int = 90
    # Sorin Code tasks can only access this directory and its descendants.
    sorin_workspace_root: Path = REPO_ROOT

    @property
    def uploads_dir(self) -> Path: return self.data_dir / "uploads"
    @property
    def reports_dir(self) -> Path: return self.data_dir / "reports"
    @property
    def exports_dir(self) -> Path: return self.data_dir / "exports"
    @property
    def backups_dir(self) -> Path: return self.data_dir / "backups"
    @property
    def cache_dir(self) -> Path: return self.data_dir / "cache"
    @property
    def logs_dir(self) -> Path: return self.data_dir / "logs"
    @property
    def sqlite_path(self) -> Path: return self.data_dir / "app.db"
    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def resolved_database_url(self) -> str:
        return self.database_url or f"sqlite:///{self.sqlite_path.as_posix()}"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.uploads_dir, self.reports_dir,
                  self.exports_dir, self.backups_dir, self.cache_dir, self.logs_dir):
            d.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings

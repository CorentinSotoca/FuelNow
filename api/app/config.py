from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://fuelnow:changeme@db:5432/fuelnow"
    source_dataset_url: str = ""
    source_format: str = "json"
    etl_cron: str = "0 6 * * *"
    etl_min_rows: int = 5000
    etl_min_ratio: float = 0.8
    rate_limit_per_min: int = 60
    search_radius_max_m: int = 30000
    cache_ttl_s: int = 900
    log_level: str = "INFO"
    alert_webhook_url: str = ""
    cors_allow_origins: str = ""

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()

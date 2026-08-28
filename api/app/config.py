from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    source_dataset_url: str = "https://data.economie.gouv.fr/api/records/1.0/download/?dataset=prix-des-carburants-en-france-flux-instantane-v2&format=json"
    source_format: str = "json"
    etl_cron: str = "0 6 * * *"
    etl_be_cron: str = "0 7 * * *"
    etl_min_rows: int = Field(5000, gt=0)
    etl_min_ratio: float = Field(0.8, ge=0, le=1)
    rate_limit_per_min: int = Field(60, gt=0)
    search_radius_max_m: int = Field(30000, gt=0)
    cache_ttl_s: int = 900
    log_level: str = "INFO"
    alert_webhook_url: str = ""
    cors_allow_origins: str = ""
    statbel_api_url: str = "https://bestat.statbel.fgov.be/bestat/api/views/9e9cf394-6c54-4d81-8013-7124a8c4bf15/result/JSON"

    @field_validator("source_dataset_url")
    @classmethod
    def validate_source_url(cls, v: str) -> str:
        if not v:
            raise ValueError("source_dataset_url must be set")
        return v

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()

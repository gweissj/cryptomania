from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    database_url: str = Field(..., env="DATABASE_URL", description="Database connection URL")
    session_token_ttl_hours: int = Field(
        default=24,
        env="SESSION_TOKEN_TTL_HOURS",
        description="Lifetime of session tokens in hours",
    )
    coingecko_base_url: str = Field(
        default="https://api.coingecko.com/api/v3",
        env="COINGECKO_BASE_URL",
        description="Base URL for the CoinGecko API",
    )


settings = Settings()

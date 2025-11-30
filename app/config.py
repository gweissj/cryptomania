from typing import Optional

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
    coingecko_demo_api_key: Optional[str] = Field(
        default=None,
        env="COINGECKO_DEMO_API_KEY",
        description="CoinGecko demo API key for v3 (header x-cg-demo-api-key)",
    )
    coingecko_api_key: Optional[str] = Field(
        default=None,
        env="COINGECKO_API_KEY",
        description="CoinGecko pro API key (header x-cg-pro-api-key)",
    )
    coincap_base_url: str = Field(
        default="https://api.coincap.io/v2",
        env="COINCAP_BASE_URL",
        description="Base URL for the CoinCap API",
    )
    coincap_graphql_url: str = Field(
        default="https://graphql.coincap.io/",
        env="COINCAP_GRAPHQL_URL",
        description="GraphQL endpoint for CoinCap API access",
    )
    coincap_api_key: Optional[str] = Field(
        default=None,
        env="COINCAP_API_KEY",
        description="CoinCap API key (Authorization: Bearer <token>)",
    )


settings = Settings()

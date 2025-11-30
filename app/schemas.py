from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl, constr, field_validator

from .utils import AgeRestrictionError, ensure_is_adult, parse_birth_date


class UserCreate(BaseModel):
    email: EmailStr
    password: constr(min_length=8)
    first_name: constr(min_length=1, max_length=100)
    last_name: constr(min_length=1, max_length=100)
    birth_date: date

    @field_validator("birth_date", mode="before")
    def parse_birth_date_value(cls, value):
        if isinstance(value, date):
            return value
        return parse_birth_date(value)

    @field_validator("birth_date")
    def validate_adult_birth_date(cls, value: date) -> date:
        try:
            ensure_is_adult(value)
        except AgeRestrictionError as exc:
            raise ValueError(str(exc)) from exc
        return value


class UserLogin(BaseModel):
    email: EmailStr
    password: constr(min_length=1)


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    first_name: Optional[constr(min_length=1, max_length=100)] = None
    last_name: Optional[constr(min_length=1, max_length=100)] = None
    password: Optional[constr(min_length=8)] = None


class UserResponse(BaseModel):
    id: int
    email: EmailStr
    first_name: str
    last_name: str
    birth_date: date
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MessageResponse(BaseModel):
    message: str


class MarketChartPoint(BaseModel):
    timestamp: int
    price: float


class MarketMover(BaseModel):
    id: str
    name: str
    symbol: str
    pair: str
    current_price: float
    change_24h_pct: float
    volume_24h: float
    image_url: Optional[HttpUrl]
    sparkline: Optional[list[float]] = None


class PortfolioAsset(BaseModel):
    id: str
    name: str
    symbol: str
    quantity: float
    current_price: float
    value: float
    change_24h_pct: float
    image_url: Optional[HttpUrl]


class CryptoDashboardResponse(BaseModel):
    currency: str
    portfolio_balance: float
    holdings_balance: float = 0.0
    cash_balance: float = 0.0
    balance_change_pct: float
    chart: list[MarketChartPoint]
    market_movers: list[MarketMover]
    portfolio: list[PortfolioAsset]
    last_updated: datetime


class WalletSummary(BaseModel):
    currency: str
    cash_balance: float
    holdings_balance: float
    total_balance: float
    balance_change_pct: float
    portfolio: list[PortfolioAsset]
    last_updated: datetime

    model_config = ConfigDict(from_attributes=True)


class WalletTransactionItem(BaseModel):
    id: int
    tx_type: str
    asset_id: Optional[str]
    asset_symbol: Optional[str]
    asset_name: Optional[str]
    quantity: float
    unit_price: float
    total_value: float
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DepositRequest(BaseModel):
    amount: float = Field(gt=0, description="Deposit amount in USD")


class BuyAssetRequest(BaseModel):
    asset_id: str
    amount_usd: float = Field(gt=0, description="How much USD to spend on the asset")
    source: Literal["coincap", "coingecko"] = Field(
        default="coincap", description="Pricing source to use for purchase"
    )


class TradeExecutionResponse(BaseModel):
    asset_id: str
    symbol: str
    name: str
    quantity: float
    price: float
    spent: float
    cash_balance: float
    total_balance: float
    executed_at: datetime
    price_source: Literal["coincap", "coingecko"]


class PriceQuote(BaseModel):
    asset_id: str
    symbol: str
    source: Literal["coincap", "coingecko"]
    price: float

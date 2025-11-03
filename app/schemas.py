from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, HttpUrl, constr, field_validator

from .utils import parse_birth_date


class UserCreate(BaseModel):
    email: EmailStr
    password: constr(min_length=8)
    first_name: constr(min_length=1, max_length=100)
    last_name: constr(min_length=1, max_length=100)
    birth_date: date
    region: constr(min_length=1, max_length=100)
    city: constr(min_length=1, max_length=100)

    @field_validator("birth_date", mode="before")
    def parse_birth_date_value(cls, value):
        if isinstance(value, date):
            return value
        return parse_birth_date(value)


class UserLogin(BaseModel):
    email: EmailStr
    password: constr(min_length=1)


class UserUpdate(BaseModel):
    first_name: Optional[constr(min_length=1, max_length=100)]
    last_name: Optional[constr(min_length=1, max_length=100)]
    birth_date: Optional[date]
    region: Optional[constr(min_length=1, max_length=100)]
    city: Optional[constr(min_length=1, max_length=100)]
    password: Optional[constr(min_length=8)]

    @field_validator("birth_date", mode="before")
    def parse_optional_birth_date(cls, value):
        if value in (None, ""):
            return None
        if isinstance(value, date):
            return value
        return parse_birth_date(value)


class UserResponse(BaseModel):
    id: int
    email: EmailStr
    first_name: str
    last_name: str
    birth_date: date
    region: str
    city: str
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
    balance_change_pct: float
    chart: list[MarketChartPoint]
    market_movers: list[MarketMover]
    portfolio: list[PortfolioAsset]
    last_updated: datetime

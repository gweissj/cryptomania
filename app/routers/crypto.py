from fastapi import APIRouter, HTTPException, Query, status

from ..schemas import CryptoDashboardResponse
from ..services.crypto import fetch_dashboard, fetch_ohlc, fetch_simple_prices


router = APIRouter(prefix="/crypto", tags=["crypto"])

ALLOWED_DAYS = {1, 7, 14, 30, 90, 180, 365}


@router.get("/prices")
async def get_prices(
    ids: str = Query(..., description="Comma-separated list of asset ids, e.g. bitcoin,ethereum"),
    vs_currency: str = Query("usd", description="Fiat currency symbol, e.g. usd, eur"),
):
    id_list = [value.strip() for value in ids.split(",") if value.strip()]
    vs_currency = vs_currency.lower()
    return await fetch_simple_prices(id_list, vs_currency)


@router.get("/ohlc")
async def get_ohlc(
    coin_id: str = Query(..., description="CoinGecko asset id, e.g. bitcoin"),
    vs_currency: str = Query("usd", description="Fiat currency symbol, e.g. usd, eur"),
    days: int = Query(30, description="Number of days for OHLC data"),
):
    if days not in ALLOWED_DAYS:
        allowed_values = ", ".join(str(value) for value in sorted(ALLOWED_DAYS))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Parameter 'days' must be one of: {allowed_values}",
        )

    return await fetch_ohlc(coin_id, vs_currency.lower(), days)


@router.get("/dashboard", response_model=CryptoDashboardResponse)
async def get_dashboard(vs_currency: str = Query("usd", description="Fiat currency symbol, e.g. usd, eur")):
    return await fetch_dashboard(vs_currency)

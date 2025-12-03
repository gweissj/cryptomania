from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user
from ..models import User
from ..schemas import (
    BuyAssetRequest,
    CryptoDashboardResponse,
    DeviceCommandAckRequest,
    DeviceCommandPollResponse,
    DeviceCommandResponse,
    DispatchDeviceCommandRequest,
    DepositRequest,
    PriceQuote,
    SellAssetRequest,
    SellDashboardResponse,
    SellExecutionResponse,
    SellPreviewResponse,
    TradeExecutionResponse,
    WalletSummary,
    WalletTransactionItem,
)
from ..services.crypto import (
    acknowledge_device_command,
    build_wallet_summary,
    build_sell_dashboard,
    buy_asset,
    deposit_funds,
    dispatch_device_command,
    fetch_dashboard,
    fetch_market_movers,
    fetch_price_quotes,
    list_wallet_transactions,
    poll_device_commands,
    search_assets,
    sell_asset,
    preview_sale,
)


router = APIRouter(prefix="/crypto", tags=["crypto"])

@router.get("/dashboard", response_model=CryptoDashboardResponse)
async def get_dashboard(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return await fetch_dashboard(db, current_user)


@router.get("/market-movers")
async def get_market_movers(limit: int = Query(6, ge=1, le=20)):
    return await fetch_market_movers(limit=limit)


@router.get("/quotes/{asset_id}", response_model=list[PriceQuote])
async def get_price_quotes(asset_id: str):
    return await fetch_price_quotes(asset_id)


@router.get("/assets")
async def get_assets(
    search: str | None = Query(None, description="Search by asset name or symbol"),
    limit: int = Query(30, ge=1, le=100),
):
    return await search_assets(search=search, limit=limit)


@router.get("/portfolio", response_model=WalletSummary)
async def get_portfolio(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return await build_wallet_summary(db, current_user)


@router.post("/deposit", response_model=WalletSummary)
async def deposit(
    payload: DepositRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return await deposit_funds(db, current_user, amount=payload.amount)


@router.post("/buy", response_model=TradeExecutionResponse)
async def buy_crypto(
    payload: BuyAssetRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return await buy_asset(
        db,
        current_user,
        asset_id=payload.asset_id,
        amount_usd=payload.amount_usd,
        price_source=payload.source,
    )


@router.get("/sell/overview", response_model=SellDashboardResponse)
async def get_sell_overview(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return await build_sell_dashboard(db, current_user)


@router.post("/sell/preview", response_model=SellPreviewResponse)
async def preview_sell(
    payload: SellAssetRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return await preview_sale(
        db,
        current_user,
        asset_id=payload.asset_id,
        quantity=payload.quantity,
        amount_usd=payload.amount_usd,
        price_source=payload.source,
    )


@router.post("/sell", response_model=SellExecutionResponse)
async def sell_crypto(
    payload: SellAssetRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return await sell_asset(
        db,
        current_user,
        asset_id=payload.asset_id,
        quantity=payload.quantity,
        amount_usd=payload.amount_usd,
        price_source=payload.source,
    )


@router.post("/device-commands", response_model=DeviceCommandResponse)
async def create_device_command(
    payload: DispatchDeviceCommandRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return await dispatch_device_command(db, current_user, payload)


@router.get("/device-commands/poll", response_model=DeviceCommandPollResponse)
async def poll_commands(
    target_device: str = Query("desktop", min_length=3, max_length=50),
    target_device_id: str | None = Query(None, min_length=1, max_length=100),
    limit: int = Query(10, ge=1, le=20),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    commands = await poll_device_commands(
        db,
        current_user,
        target_device=target_device,
        target_device_id=target_device_id,
        limit=limit,
    )
    return DeviceCommandPollResponse(
        commands=commands,
        polled_at=datetime.now(timezone.utc),
    )


@router.post(
    "/device-commands/{command_id}/ack",
    response_model=DeviceCommandResponse,
    summary="Acknowledge or reject a device command",
)
async def acknowledge_command(
    payload: DeviceCommandAckRequest,
    command_id: int = Path(..., ge=1),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return await acknowledge_device_command(
        db,
        current_user,
        command_id=command_id,
        status=payload.status,
    )


@router.get("/transactions", response_model=list[WalletTransactionItem])
async def get_transactions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    transactions = await list_wallet_transactions(db, current_user)
    return [
        WalletTransactionItem(
            id=tx.id,
            tx_type=tx.tx_type,
            asset_id=tx.asset_id,
            asset_symbol=tx.asset_symbol,
            asset_name=tx.asset_name,
            quantity=tx.quantity,
            unit_price=tx.unit_price,
            total_value=tx.total_value,
            created_at=tx.created_at,
        )
        for tx in transactions
    ]

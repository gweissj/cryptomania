from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Set, Tuple

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from ..models import User, Wallet, WalletHolding, WalletTransaction
from ..schemas import (
    CryptoDashboardResponse,
    MarketChartPoint,
    MarketMover,
    PortfolioAsset,
    PriceQuote,
    TradeExecutionResponse,
    WalletSummary,
)
from .coincap import fetch_asset, fetch_assets, fetch_assets_by_ids, fetch_history, fetch_top_assets
from .coingecko import fetch_market_overview, fetch_price_usd

_CHART_ASSET_ID = "bitcoin"
_CHART_DAYS = 7


def _icon_for_symbol(symbol: str | None) -> str | None:
    if not symbol:
        return None
    return f"https://assets.coincap.io/assets/icons/{symbol.lower()}@2x.png"


async def _ensure_wallet(db: Session, user: User) -> Wallet:
    wallet = user.wallet
    if wallet is None:
        wallet = Wallet(user_id=user.id, base_currency="USD", cash_balance=0.0)
        db.add(wallet)
        db.commit()
        db.refresh(wallet)
    return wallet


def _compute_portfolio_assets(
    holdings: Iterable[WalletHolding],
    quotes: Dict[str, Dict[str, object]],
) -> Tuple[List[PortfolioAsset], float, float]:
    items: List[PortfolioAsset] = []
    current_balance = 0.0
    previous_balance = 0.0

    for holding in holdings:
        quote = quotes.get(holding.asset_id)
        if quote is None:
            continue

        price = float(quote.get("priceUsd") or 0.0)
        change_pct = float(quote.get("changePercent24Hr") or 0.0)
        value = price * holding.quantity
        current_balance += value

        if change_pct > -100.0:
            previous_price = price / (1 + change_pct / 100)
            previous_balance += previous_price * holding.quantity

        items.append(
            PortfolioAsset(
                id=holding.asset_id,
                name=str(quote.get("name") or holding.name),
                symbol=str(quote.get("symbol") or holding.symbol).upper(),
                quantity=float(holding.quantity),
                current_price=price,
                value=value,
                change_24h_pct=change_pct,
                image_url=_icon_for_symbol(str(quote.get("symbol", ""))),
            )
        )

    return items, current_balance, previous_balance


def _build_fallback_market_movers(
    assets: Iterable[Dict[str, Any]],
    limit: int,
    exclude_ids: Set[str] | None = None,
) -> List[MarketMover]:
    fallback: List[MarketMover] = []
    seen_ids: Set[str] = set(exclude_ids or ())

    for asset in assets:
        if len(fallback) >= limit:
            break
        if not isinstance(asset, dict):
            continue

        asset_id = str(asset.get("id") or "").strip()
        symbol = str(asset.get("symbol") or "").strip().upper()
        if not asset_id or not symbol or asset_id in seen_ids:
            continue

        seen_ids.add(asset_id)
        fallback.append(
            MarketMover(
                id=asset_id,
                name=str(asset.get("name") or ""),
                symbol=symbol,
                pair=f"{symbol}/USD",
                current_price=float(asset.get("priceUsd") or 0.0),
                change_24h_pct=float(asset.get("changePercent24Hr") or 0.0),
                volume_24h=float(asset.get("volumeUsd24Hr") or 0.0),
                image_url=_icon_for_symbol(symbol),
                sparkline=None,
            )
        )

    return fallback


async def build_wallet_summary(db: Session, user: User) -> WalletSummary:
    wallet = await _ensure_wallet(db, user)
    holdings = list(wallet.holdings)
    quotes = await fetch_assets_by_ids([holding.asset_id for holding in holdings])
    portfolio_items, holdings_balance, previous_balance = _compute_portfolio_assets(
        holdings, quotes
    )

    cash_balance = float(wallet.cash_balance or 0.0)
    total_balance = holdings_balance + cash_balance
    previous_total = previous_balance + cash_balance
    balance_change_pct = 0.0
    if previous_total > 0:
        balance_change_pct = (total_balance / previous_total - 1) * 100

    return WalletSummary(
        currency=wallet.base_currency.upper(),
        cash_balance=cash_balance,
        holdings_balance=holdings_balance,
        total_balance=total_balance,
        balance_change_pct=balance_change_pct,
        portfolio=portfolio_items,
        last_updated=datetime.now(timezone.utc),
    )


async def fetch_market_movers(limit: int = 6) -> List[MarketMover]:
    limit = max(1, limit)

    def _normalize(value: str | None) -> str:
        if not value:
            return ""
        return "".join(ch for ch in value.lower() if ch.isalnum())

    try:
        markets = await fetch_market_overview(limit=limit * 3)
    except HTTPException:
        markets = []

    try:
        top_assets = await fetch_top_assets(limit=max(limit * 5, 100))
    except HTTPException:
        top_assets = []

    assets_by_symbol: Dict[str, List[Dict[str, Any]]] = {}
    assets_by_name: Dict[str, Dict[str, Any]] = {}
    for asset in top_assets:
        if not isinstance(asset, dict):
            continue
        asset_id = str(asset.get("id") or "").strip()
        symbol = str(asset.get("symbol") or "").upper()
        name = str(asset.get("name") or "")
        if not asset_id or not symbol:
            continue
        assets_by_symbol.setdefault(symbol, []).append(asset)
        normalized_name = _normalize(name)
        if normalized_name and normalized_name not in assets_by_name:
            assets_by_name[normalized_name] = asset

    movers: List[MarketMover] = []
    used_ids: Set[str] = set()

    for market in markets:
        if len(movers) >= limit:
            break
        if not isinstance(market, dict):
            continue

        symbol = str(market.get("symbol") or "").upper()
        if not symbol:
            continue

        matched_asset: Dict[str, Any] | None = None
        for candidate in assets_by_symbol.get(symbol, []):
            candidate_id = str(candidate.get("id") or "").strip()
            if candidate_id and candidate_id not in used_ids:
                matched_asset = candidate
                break

        if matched_asset is None:
            normalized_market_name = _normalize(str(market.get("name") or ""))
            candidate = assets_by_name.get(normalized_market_name)
            candidate_id = str(candidate.get("id") or "").strip() if candidate else ""
            if candidate and candidate_id and candidate_id not in used_ids:
                matched_asset = candidate

        if matched_asset is None:
            continue

        asset_id = str(matched_asset.get("id") or "").strip()
        used_ids.add(asset_id)

        price = float(market.get("current_price") or matched_asset.get("priceUsd") or 0.0)
        change_pct = float(
            market.get("price_change_percentage_24h") or matched_asset.get("changePercent24Hr") or 0.0
        )
        volume_24h = float(market.get("total_volume") or matched_asset.get("volumeUsd24Hr") or 0.0)
        sparkline_raw = (
            (market.get("sparkline_in_7d") or {}).get("price") if isinstance(market, dict) else None
        )
        sparkline: List[float] | None = None
        if isinstance(sparkline_raw, list):
            sparkline = [float(value) for value in sparkline_raw if isinstance(value, (int, float))]

        image_url = str(market.get("image") or "").strip() or _icon_for_symbol(symbol)
        movers.append(
            MarketMover(
                id=asset_id,
                name=str(matched_asset.get("name") or market.get("name") or ""),
                symbol=symbol,
                pair=f"{symbol}/USD",
                current_price=price,
                change_24h_pct=change_pct,
                volume_24h=volume_24h,
                image_url=image_url,
                sparkline=sparkline,
            )
        )

    if len(movers) < limit and top_assets:
        fallback_needed = limit - len(movers)
        fallback = _build_fallback_market_movers(
            top_assets,
            limit=fallback_needed,
            exclude_ids=used_ids,
        )
        movers.extend(fallback)

    return movers


async def fetch_price_quotes(asset_id: str) -> List[PriceQuote]:
    asset = await fetch_asset(asset_id)
    symbol = str(asset.get("symbol") or asset_id).upper()
    name = str(asset.get("name") or asset_id)
    price_coincap = float(asset.get("priceUsd") or 0.0)
    quotes: List[PriceQuote] = [
        PriceQuote(asset_id=asset_id, symbol=symbol, source="coincap", price=price_coincap)
    ]

    try:
        price_gecko = await fetch_price_usd(symbol, asset_id_hint=asset_id, asset_name=name)
        quotes.append(
            PriceQuote(
                asset_id=asset_id,
                symbol=symbol,
                source="coingecko",
                price=price_gecko,
            )
        )
    except HTTPException:
        # Ignore CoinGecko failures; CoinCap quote will still be returned.
        pass

    # Ensure deterministic order: cheaper first to simplify client-side highlighting.
    quotes_sorted = sorted(quotes, key=lambda q: q.price)
    return quotes_sorted


async def fetch_dashboard(db: Session, user: User) -> CryptoDashboardResponse:
    wallet = await _ensure_wallet(db, user)
    summary = await build_wallet_summary(db, user)

    history = await fetch_history(_CHART_ASSET_ID, days=_CHART_DAYS)
    chart_points = [
        MarketChartPoint(
            timestamp=int(point.get("time") or 0),
            price=float(point.get("priceUsd") or 0.0),
        )
        for point in history
    ]

    market_movers = await fetch_market_movers(limit=6)

    return CryptoDashboardResponse(
        currency=summary.currency,
        portfolio_balance=summary.total_balance,
        holdings_balance=summary.holdings_balance,
        cash_balance=summary.cash_balance,
        balance_change_pct=summary.balance_change_pct,
        chart=chart_points,
        market_movers=market_movers,
        portfolio=summary.portfolio,
        last_updated=summary.last_updated,
    )


async def deposit_funds(db: Session, user: User, amount: float) -> WalletSummary:
    if amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Deposit amount must be greater than zero",
        )
    wallet = await _ensure_wallet(db, user)
    wallet.cash_balance += amount
    db.add(
        WalletTransaction(
            wallet_id=wallet.id,
            tx_type="DEPOSIT",
            quantity=0.0,
            unit_price=1.0,
            total_value=amount,
        )
    )
    db.commit()
    db.refresh(wallet)
    return await build_wallet_summary(db, user)


async def buy_asset(
    db: Session,
    user: User,
    asset_id: str,
    amount_usd: float,
    price_source: str = "coincap",
) -> TradeExecutionResponse:
    if amount_usd <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Purchase amount must be greater than zero",
        )

    wallet = await _ensure_wallet(db, user)
    if wallet.cash_balance < amount_usd:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Not enough cash balance for this purchase. Deposit funds first.",
        )

    asset = await fetch_asset(asset_id)
    symbol = str(asset.get("symbol") or "").upper()
    name = str(asset.get("name") or asset_id)

    if price_source not in {"coincap", "coingecko"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported price source",
        )

    if price_source == "coingecko":
        price = await fetch_price_usd(symbol, asset_id_hint=asset_id, asset_name=name)
    else:
        price = float(asset.get("priceUsd") or 0.0)

    if price <= 0:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Received zero price for the requested asset",
        )

    quantity = amount_usd / price

    holding = next((h for h in wallet.holdings if h.asset_id == asset_id), None)
    if holding is None:
        holding = WalletHolding(
            wallet_id=wallet.id,
            asset_id=asset_id,
            symbol=symbol,
            name=name,
            quantity=0.0,
            total_cost=0.0,
            avg_buy_price=0.0,
        )
        db.add(holding)

    holding.quantity += quantity
    holding.total_cost += amount_usd
    holding.avg_buy_price = holding.total_cost / holding.quantity if holding.quantity > 0 else 0.0

    wallet.cash_balance -= amount_usd

    db.add(
        WalletTransaction(
            wallet_id=wallet.id,
            asset_id=asset_id,
            asset_symbol=symbol,
            asset_name=name,
            tx_type="BUY",
            quantity=quantity,
            unit_price=price,
            total_value=amount_usd,
        )
    )
    db.add(wallet)
    db.add(holding)
    db.commit()
    db.refresh(wallet)

    summary = await build_wallet_summary(db, user)
    return TradeExecutionResponse(
        asset_id=asset_id,
        symbol=symbol,
        name=name,
        quantity=quantity,
        price=price,
        spent=amount_usd,
        cash_balance=summary.cash_balance,
        total_balance=summary.total_balance,
        executed_at=summary.last_updated,
        price_source="coingecko" if price_source == "coingecko" else "coincap",
    )


async def list_wallet_transactions(db: Session, user: User) -> List[WalletTransaction]:
    wallet = await _ensure_wallet(db, user)
    return (
        db.query(WalletTransaction)
        .filter(WalletTransaction.wallet_id == wallet.id)
        .order_by(WalletTransaction.created_at.desc())
        .limit(50)
        .all()
    )


async def search_assets(search: str | None = None, limit: int = 30) -> List[MarketMover]:
    assets = await fetch_assets(search=search, limit=limit)
    movers: List[MarketMover] = []
    for asset in assets:
        symbol = str(asset.get("symbol") or "").upper()
        price = float(asset.get("priceUsd") or 0.0)
        change_pct = float(asset.get("changePercent24Hr") or 0.0)
        volume_24h = float(asset.get("volumeUsd24Hr") or 0.0)
        movers.append(
            MarketMover(
                id=str(asset.get("id") or ""),
                name=str(asset.get("name") or ""),
                symbol=symbol,
                pair=f"{symbol}/USD",
                current_price=price,
                change_24h_pct=change_pct,
                volume_24h=volume_24h,
                image_url=_icon_for_symbol(symbol),
            )
        )
    return movers

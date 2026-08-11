import hashlib
import json
from dataclasses import asdict
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
from time import time

from .clob_types import (
    BuilderFeeRate,
    OrderBookSummary,
    OrderSummary,
    OrderType,
    TickSize,
)
from .constants import BYTES32_ZERO
from .order_utils import SignatureTypeV2, Side, SideString

MIN_GTD_EXPIRATION_SECONDS = 3 * 60
FEE_QUANTUM = Decimal("0.00001")
USDC_SCALE = Decimal("1000000")


def parse_raw_orderbook_summary(raw_obs: any) -> OrderBookSummary:
    bids = []
    for bid in raw_obs["bids"]:
        bids.append(OrderSummary(size=bid["size"], price=bid["price"]))

    asks = []
    for ask in raw_obs["asks"]:
        asks.append(OrderSummary(size=ask["size"], price=ask["price"]))

    orderbookSummary = OrderBookSummary(
        market=raw_obs["market"],
        asset_id=raw_obs["asset_id"],
        timestamp=raw_obs["timestamp"],
        last_trade_price=raw_obs["last_trade_price"],
        min_order_size=raw_obs["min_order_size"],
        neg_risk=raw_obs["neg_risk"],
        tick_size=raw_obs["tick_size"],
        bids=bids,
        asks=asks,
        hash=raw_obs["hash"],
    )

    return orderbookSummary


def generate_orderbook_summary_hash(orderbook: OrderBookSummary) -> str:
    """
    Server-compatible orderbook hash.

    The server computes SHA1 over a compact JSON payload with a specific key order,
    and with the "hash" field set to an empty string while hashing.
    """

    # Go server-side payload field order (struct order):
    # market, asset_id, timestamp, hash, bids, asks, min_order_size, tick_size, neg_risk, last_trade_price
    payload = {
        "market": orderbook.market,
        "asset_id": orderbook.asset_id,
        "timestamp": orderbook.timestamp,
        "hash": "",
        "bids": [{"price": o.price, "size": o.size} for o in (orderbook.bids or [])],
        "asks": [{"price": o.price, "size": o.size} for o in (orderbook.asks or [])],
        "min_order_size": orderbook.min_order_size,
        "tick_size": orderbook.tick_size,
        "neg_risk": orderbook.neg_risk,
        "last_trade_price": orderbook.last_trade_price,
    }

    serialized = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    h = hashlib.sha1(serialized.encode("utf-8")).hexdigest()
    orderbook.hash = h
    return h


def order_to_json(order, owner, orderType, post_only: bool = False) -> dict:
    if int(order.signatureType) != int(SignatureTypeV2.DEPOSIT_WALLET):
        raise ValueError(
            "Kuest order submission supports only Deposit Wallet signature type 3"
        )

    _validate_gtd_expiration(order.expiration, orderType)

    order_payload = asdict(order)
    order_payload["salt"] = int(order.salt)
    order_payload["side"] = (
        SideString.BUY if order.side == Side.BUY else SideString.SELL
    )
    order_payload["signatureType"] = int(order.signatureType)

    return {
        "order": order_payload,
        "owner": owner,
        "orderType": orderType,
        "postOnly": post_only,
    }


def _validate_gtd_expiration(expiration, orderType):
    if orderType != OrderType.GTD:
        return

    try:
        expiration_timestamp = int(expiration)
    except (TypeError, ValueError):
        raise ValueError("GTD expiration must be a Unix timestamp in seconds")

    minimum_expiration = int(time()) + MIN_GTD_EXPIRATION_SECONDS
    if expiration_timestamp < minimum_expiration:
        raise ValueError("GTD expiration must be at least 3 minutes in the future")


def is_tick_size_smaller(a: TickSize, b: TickSize) -> bool:
    return float(a) < float(b)


def price_valid(price: float, tick_size: TickSize) -> bool:
    return price >= float(tick_size) and price <= 1 - float(tick_size)


def builder_code_to_bytes32(builder_code: str = None) -> str:
    value = (builder_code or "").strip()
    if not value or value == BYTES32_ZERO:
        return BYTES32_ZERO

    hex_value = value[2:] if value.startswith(("0x", "0X")) else value
    if len(hex_value) == 40 and all(c in "0123456789abcdefABCDEF" for c in hex_value):
        return "0x" + hex_value.rjust(64, "0").lower()
    if len(hex_value) == 64 and all(c in "0123456789abcdefABCDEF" for c in hex_value):
        return "0x" + hex_value.lower()

    raise ValueError("builder_code must be an address or bytes32 hex string")


def parse_builder_fee_rate_response(value) -> BuilderFeeRate:
    response = value if isinstance(value, dict) else {}
    maker_flat = int(response.get("builder_maker_flat_fee_bps") or 0)
    taker_share = int(response.get("builder_taker_fee_share_bps") or 3000)
    if maker_flat < 0:
        raise ValueError("builder_maker_flat_fee_bps must be non-negative")
    if taker_share < 0 or taker_share >= 10_000:
        raise ValueError("builder_taker_fee_share_bps must be between 0 and 9999")
    return BuilderFeeRate(maker_flat=maker_flat, taker_share=taker_share)


def calculate_dynamic_fee_breakdown(
    shares: float,
    price: float,
    rate: float,
    exponent: float,
    builder_taker_fee_share_bps: int = 3000,
) -> dict:
    """Mirror the CLOB five-decimal fee rounding and on-chain USDC split."""
    if not 0 < price < 1:
        raise ValueError(
            f"price {price} must be between 0 and 1 for dynamic fee calculation"
        )
    if (
        not isinstance(builder_taker_fee_share_bps, int)
        or builder_taker_fee_share_bps < 0
        or builder_taker_fee_share_bps >= 10_000
    ):
        raise ValueError(
            "builder_taker_fee_share_bps must be an integer between 0 and 9999"
        )

    decimal_price = Decimal(str(price))
    raw_base = (
        Decimal(str(shares))
        * Decimal(str(rate))
        * (decimal_price * (Decimal(1) - decimal_price)) ** Decimal(str(exponent))
    )
    if raw_base < FEE_QUANTUM:
        return {
            "kuest_fee_base": 0.0,
            "kuest_fee": 0.0,
            "operator_fee": 0.0,
            "total_fee": 0.0,
        }

    kuest_fee_base = raw_base.quantize(FEE_QUANTUM, rounding=ROUND_HALF_UP)
    total_fee = (
        kuest_fee_base * Decimal(10_000) / Decimal(10_000 - builder_taker_fee_share_bps)
    ).quantize(FEE_QUANTUM, rounding=ROUND_CEILING)
    total_micro_usdc = int(total_fee * USDC_SCALE)
    operator_micro_usdc = total_micro_usdc * builder_taker_fee_share_bps // 10_000
    return {
        "kuest_fee_base": float(kuest_fee_base),
        "kuest_fee": float(
            Decimal(total_micro_usdc - operator_micro_usdc) / USDC_SCALE
        ),
        "operator_fee": float(Decimal(operator_micro_usdc) / USDC_SCALE),
        "total_fee": float(Decimal(total_micro_usdc) / USDC_SCALE),
    }


def adjust_market_buy_amount_for_fees(
    amount: float,
    price: float,
    user_usdc_balance: float,
    kuest_taker_fee_rate_bps: int,
    builder_taker_fee_share_bps: int,
) -> float:
    builder_share = min(9_999, max(0, builder_taker_fee_share_bps)) / 10_000
    total_fee_rate = kuest_taker_fee_rate_bps / 10_000 / (1 - builder_share)
    total_cost = amount * (1 + total_fee_rate)
    if user_usdc_balance >= total_cost:
        return amount

    adjusted = user_usdc_balance / (1 + total_fee_rate)
    if not adjusted > 0:
        raise ValueError(
            f"user_usdc_balance {user_usdc_balance} too small to cover fees at price {price}"
        )
    return adjusted


def adjust_market_buy_amount_for_dynamic_fees(
    amount: float,
    price: float,
    user_usdc_balance: float,
    rate: float,
    exponent: float,
    builder_taker_fee_share_bps: int,
) -> float:
    """Fit a BUY amount plus the grossed-up dynamic taker fee in balance."""
    if not 0 < price < 1:
        raise ValueError(
            f"price {price} must be between 0 and 1 for dynamic fee calculation"
        )

    def fee_for_amount(principal: float) -> float:
        return calculate_dynamic_fee_breakdown(
            principal / price,
            price,
            rate,
            exponent,
            builder_taker_fee_share_bps,
        )["total_fee"]

    if user_usdc_balance >= amount + fee_for_amount(amount):
        return amount

    low = 0
    high = int(min(amount, user_usdc_balance) * 1_000_000)
    best = 0
    while low <= high:
        mid = (low + high) // 2
        principal = mid / 1_000_000
        if principal + fee_for_amount(principal) <= user_usdc_balance:
            best = mid
            low = mid + 1
        else:
            high = mid - 1

    if best == 0:
        raise ValueError(
            f"user_usdc_balance {user_usdc_balance} too small to cover fees at price {price}"
        )
    return best / 1_000_000

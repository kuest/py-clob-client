import hashlib
import json
from dataclasses import asdict
from time import time

from .clob_types import OrderBookSummary, OrderSummary, OrderType, TickSize
from .constants import BYTES32_ZERO
from .order_utils import SignatureTypeV2, Side, SideString

MIN_GTD_EXPIRATION_SECONDS = 3 * 60


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


def adjust_market_buy_amount_for_fees(
    amount: float,
    price: float,
    user_usdc_balance: float,
    kuest_taker_fee_rate_bps: int,
    builder_taker_fee_rate_bps: int,
) -> float:
    total_fee_rate = (kuest_taker_fee_rate_bps + builder_taker_fee_rate_bps) / 10_000
    total_cost = amount * (1 + total_fee_rate)
    if user_usdc_balance >= total_cost:
        return amount

    adjusted = user_usdc_balance / (1 + total_fee_rate)
    if adjusted <= 0:
        raise ValueError(
            f"user_usdc_balance {user_usdc_balance} too small to cover fees at price {price}"
        )
    return adjusted

from time import time
from unittest import TestCase

from py_clob_client.clob_types import CreateOrderOptions, OrderArgs, OrderType
from py_clob_client.constants import AMOY
from py_clob_client.order_builder.builder import OrderBuilder
from py_clob_client.order_builder.constants import BUY
from py_clob_client.signer import Signer
from py_clob_client.utilities import (
    MIN_GTD_EXPIRATION_SECONDS,
    generate_orderbook_summary_hash,
    is_tick_size_smaller,
    order_to_json,
    parse_raw_orderbook_summary,
    price_valid,
)

PRIVATE_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
DEPOSIT_WALLET = "0x1111111111111111111111111111111111111111"
EXPIRATION_BUFFER_SECONDS = 10


class TestUtilities(TestCase):
    def test_parse_raw_orderbook_summary_and_hash(self):
        raw_obs = {
            "market": "0xaabbcc",
            "asset_id": "100",
            "bids": [
                {"price": "0.3", "size": "100"},
                {"price": "0.4", "size": "100"},
            ],
            "asks": [
                {"price": "0.6", "size": "100"},
                {"price": "0.7", "size": "100"},
            ],
            "hash": "",
            "timestamp": "123456789",
            "min_order_size": "100",
            "neg_risk": False,
            "tick_size": "0.01",
            "last_trade_price": "0.5",
        }

        orderbook_summary = parse_raw_orderbook_summary(raw_obs)

        self.assertEqual(orderbook_summary.market, "0xaabbcc")
        self.assertEqual(orderbook_summary.asset_id, "100")
        self.assertEqual(len(orderbook_summary.bids), 2)
        self.assertEqual(len(orderbook_summary.asks), 2)
        self.assertEqual(
            generate_orderbook_summary_hash(orderbook_summary),
            "0458ea5755c9f73d64a14636fa5c36ed460ec394",
        )

    def test_tick_size_helpers(self):
        self.assertTrue(is_tick_size_smaller("0.01", "0.1"))
        self.assertFalse(is_tick_size_smaller("0.1", "0.01"))
        self.assertTrue(price_valid(0.5, "0.01"))
        self.assertFalse(price_valid(0.995, "0.01"))

    def test_order_to_json_is_deposit_wallet_type_3_only(self):
        signer = Signer(private_key=PRIVATE_KEY, chain_id=AMOY)
        builder = OrderBuilder(signer, funder=DEPOSIT_WALLET)
        order = builder.create_order(
            order_args=OrderArgs(
                token_id="100",
                price=0.5,
                size=100,
                side=BUY,
            ),
            options=CreateOrderOptions(tick_size="0.1", neg_risk=False),
        )

        payload = order_to_json(
            order=order,
            owner="owner-api-key",
            orderType=OrderType.GTC,
        )

        order_payload = payload["order"]
        self.assertEqual(order_payload["maker"], DEPOSIT_WALLET)
        self.assertEqual(order_payload["signer"], DEPOSIT_WALLET)
        self.assertEqual(order_payload["signatureType"], 3)
        self.assertNotIn("feeRateBps", order_payload)
        self.assertNotIn("nonce", order_payload)
        self.assertNotIn("taker", order_payload)

    def test_order_to_json_rejects_short_gtd_expiration(self):
        signer = Signer(private_key=PRIVATE_KEY, chain_id=AMOY)
        builder = OrderBuilder(signer, funder=DEPOSIT_WALLET)
        order = builder.create_order(
            order_args=OrderArgs(
                token_id="100",
                price=0.5,
                size=100,
                side=BUY,
                expiration=int(time()) + 60,
            ),
            options=CreateOrderOptions(tick_size="0.1", neg_risk=False),
        )

        with self.assertRaisesRegex(ValueError, "at least 3 minutes"):
            order_to_json(
                order=order,
                owner="owner-api-key",
                orderType=OrderType.GTD,
            )

    def test_order_to_json_accepts_gtd_expiration_above_minimum(self):
        signer = Signer(private_key=PRIVATE_KEY, chain_id=AMOY)
        builder = OrderBuilder(signer, funder=DEPOSIT_WALLET)
        expiration = int(time()) + MIN_GTD_EXPIRATION_SECONDS + EXPIRATION_BUFFER_SECONDS
        order = builder.create_order(
            order_args=OrderArgs(
                token_id="100",
                price=0.5,
                size=100,
                side=BUY,
                expiration=expiration,
            ),
            options=CreateOrderOptions(tick_size="0.1", neg_risk=False),
        )

        payload = order_to_json(
            order=order,
            owner="owner-api-key",
            orderType=OrderType.GTD,
        )

        self.assertEqual(payload["order"]["expiration"], str(expiration))

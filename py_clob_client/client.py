import logging
import json
import time
from dataclasses import replace
from typing import Any, Optional
from urllib.parse import quote

from py_builder_signing_sdk.config import BuilderConfig

from .order_builder.builder import OrderBuilder
from .headers.headers import (
    create_level_1_headers,
    create_level_2_headers,
    enrich_l2_headers_with_builder_headers,
)
from .signer import Signer
from .config import get_contract_config
from .order_utils import SignatureTypeV2

from .endpoints import (
    CANCEL,
    CANCEL_ORDERS,
    CANCEL_MARKET_ORDERS,
    CANCEL_ALL,
    CREATE_API_KEY,
    DELETE_API_KEY,
    DERIVE_API_KEY,
    GET_API_KEYS,
    CLOSED_ONLY,
    CREATE_READONLY_API_KEY,
    GET_READONLY_API_KEYS,
    DELETE_READONLY_API_KEY,
    VALIDATE_READONLY_API_KEY,
    GET_LAST_TRADE_PRICE,
    GET_ORDER,
    GET_ORDER_BOOK,
    MID_POINT,
    ORDERS,
    POST_ORDER,
    POST_ORDERS,
    PRICE,
    TIME,
    TRADES,
    GET_NOTIFICATIONS,
    DROP_NOTIFICATIONS,
    GET_BALANCE_ALLOWANCE,
    UPDATE_BALANCE_ALLOWANCE,
    IS_ORDER_SCORING,
    GET_TICK_SIZE,
    GET_NEG_RISK,
    ARE_ORDERS_SCORING,
    GET_SIMPLIFIED_MARKETS,
    GET_MARKETS,
    GET_MARKET,
    GET_CLOB_MARKET,
    GET_MARKETS_BY_TOKEN,
    GET_SAMPLING_SIMPLIFIED_MARKETS,
    GET_SAMPLING_MARKETS,
    GET_MARKET_TRADES_EVENTS,
    GET_LAST_TRADES_PRICES,
    MID_POINTS,
    GET_ORDER_BOOKS,
    GET_PRICES,
    GET_SPREAD,
    GET_SPREADS,
    GET_BUILDER_TRADES,
    GET_BUILDER_FEE_RATE,
    POST_HEARTBEAT,
    VERSION,
)
from .clob_types import (
    ApiCreds,
    ReadonlyApiKeyResponse,
    TradeParams,
    OpenOrderParams,
    OrderArgs,
    RequestArgs,
    DropNotificationParams,
    OrderBookSummary,
    BalanceAllowanceParams,
    OrderScoringParams,
    TickSize,
    CreateOrderOptions,
    OrdersScoringParams,
    OrderType,
    PartialCreateOrderOptions,
    BookParams,
    MarketOrderArgs,
    MarketByTokenResponse,
    PostOrdersArgs,
    FeeInfo,
    BuilderFeeRate,
)
from .exceptions import PolyException
from .http_helpers.helpers import (
    add_query_trade_params,
    add_query_open_orders_params,
    delete,
    get,
    post,
    drop_notifications_query_params,
    add_balance_allowance_params_to_url,
    add_order_scoring_params_to_url,
)

from .constants import (
    L0,
    L1,
    L1_AUTH_UNAVAILABLE,
    L2,
    L2_AUTH_UNAVAILABLE,
    END_CURSOR,
    BUILDER_AUTH_UNAVAILABLE,
    BYTES32_ZERO,
)
from .utilities import (
    parse_raw_orderbook_summary,
    generate_orderbook_summary_hash,
    order_to_json,
    is_tick_size_smaller,
    price_valid,
    builder_code_to_bytes32,
    parse_builder_fee_rate_response,
    adjust_market_buy_amount_for_dynamic_fees,
)
from .rfq import RfqClient
from .site_config import GEOBLOCK_HOST, SITE_CONFIG, get_site_order_context
from .site_scope import (
    filter_site_scoped_markets,
    get_site_market_scope,
    has_configured_site_scope,
)


def apply_site_order_context(order_args):
    context = get_site_order_context()
    if not context:
        return order_args
    return replace(order_args, **context)


class ClobClient:
    def __init__(
        self,
        host,
        chain_id: int = None,
        key: str = None,
        creds: ApiCreds = None,
        signature_type: int = None,
        funder: str = None,
        builder_config: BuilderConfig = None,
        tick_size_ttl: float = 300.0,
    ):
        """
        Initializes the clob client
        The client can be started in 3 modes:
        1) Level 0: Requires only the clob host url
                    Allows access to open CLOB endpoints

        2) Level 1: Requires the host, chain_id and a private key.
                    Allows access to L1 authenticated endpoints + all unauthenticated endpoints

        3) Level 2: Requires the host, chain_id, a private key, and Credentials.
                    Allows access to all endpoints
        """
        self.host = host[0:-1] if host.endswith("/") else host
        self.chain_id = chain_id
        self.signer = Signer(key, chain_id) if key else None
        self.creds = creds
        self.mode = self._get_client_mode()
        if signature_type is not None and int(signature_type) != int(
            SignatureTypeV2.DEPOSIT_WALLET
        ):
            raise ValueError(
                "Kuest order flow supports only Deposit Wallet signature type 3"
            )

        if self.signer:
            self.builder = OrderBuilder(
                self.signer,
                sig_type=signature_type or SignatureTypeV2.DEPOSIT_WALLET,
                funder=funder,
            )

        self.builder_config = None
        if builder_config:
            self.builder_config = builder_config

        # local cache
        self.__tick_sizes = {}
        self.__tick_size_timestamps = {}
        self.__tick_size_ttl = tick_size_ttl
        self.__neg_risk = {}
        self.__fee_infos = {}
        self.__builder_fee_rates = {}
        self.__token_condition_map = {}
        self._geoblock_status = None

        # RFQ client
        self.rfq = RfqClient(self)

        self.logger = logging.getLogger(self.__class__.__name__)

    def get_address(self):
        """
        Returns the public address of the signer
        """
        return self.signer.address() if self.signer else None

    def get_collateral_address(self):
        """
        Returns the collateral token address
        """
        contract_config = get_contract_config(self.chain_id)
        if contract_config:
            return contract_config.collateral

    def get_conditional_address(self):
        """
        Returns the conditional token address
        """
        contract_config = get_contract_config(self.chain_id)
        if contract_config:
            return contract_config.conditional_tokens

    def get_exchange_address(self, neg_risk=False):
        """
        Returns the exchange address
        """
        contract_config = get_contract_config(self.chain_id, neg_risk)
        if contract_config:
            return contract_config.exchange

    def get_ok(self):
        """
        Health check: Confirms that the server is up
        Does not need authentication
        """
        return get("{}/".format(self.host))

    def get_server_time(self):
        """
        Returns the current timestamp on the server
        Does not need authentication
        """
        return get("{}{}".format(self.host, TIME))

    def get_version(self) -> int:
        """
        Returns the CLOB API version. Defaults to V2 when the response omits it.
        """
        try:
            result = get("{}{}".format(self.host, VERSION))
            return result.get("version", 2) if isinstance(result, dict) else 2
        except Exception:
            return 2

    def create_api_key(self, nonce: int = None) -> ApiCreds:
        """
        Creates a new CLOB API key for the given
        """
        self.assert_level_1_auth()

        endpoint = "{}{}".format(self.host, CREATE_API_KEY)
        headers = create_level_1_headers(self.signer, nonce)

        creds_raw = post(endpoint, headers=headers)
        try:
            creds = ApiCreds(
                api_key=creds_raw["apiKey"],
                api_secret=creds_raw["secret"],
                api_passphrase=creds_raw["passphrase"],
            )
        except:
            self.logger.error("Couldn't parse created CLOB creds")
            return None
        return creds

    def derive_api_key(self, nonce: int = None) -> ApiCreds:
        """
        Derives an already existing CLOB API key for the given address and nonce
        """
        self.assert_level_1_auth()

        endpoint = "{}{}".format(self.host, DERIVE_API_KEY)
        headers = create_level_1_headers(self.signer, nonce)

        creds_raw = get(endpoint, headers=headers)
        try:
            creds = ApiCreds(
                api_key=creds_raw["apiKey"],
                api_secret=creds_raw["secret"],
                api_passphrase=creds_raw["passphrase"],
            )
        except:
            self.logger.error("Couldn't parse derived CLOB creds")
            return None
        return creds

    def create_or_derive_api_creds(self, nonce: int = None) -> ApiCreds:
        """
        Creates API creds if not already created for nonce, otherwise derives them
        """
        try:
            return self.create_api_key(nonce)
        except:
            return self.derive_api_key(nonce)

    def set_api_creds(self, creds: ApiCreds):
        """
        Sets client api creds
        """
        self.creds = creds
        self.mode = self._get_client_mode()

    def get_api_keys(self):
        """
        Gets the available API keys for this address
        Level 2 Auth required
        """
        self.assert_level_2_auth()

        request_args = RequestArgs(method="GET", request_path=GET_API_KEYS)
        headers = create_level_2_headers(self.signer, self.creds, request_args)
        return get("{}{}".format(self.host, GET_API_KEYS), headers=headers)

    def get_closed_only_mode(self):
        """
        Gets the closed only mode flag for thsi address
        Level 2 Auth required
        """
        self.assert_level_2_auth()

        request_args = RequestArgs(method="GET", request_path=CLOSED_ONLY)
        headers = create_level_2_headers(self.signer, self.creds, request_args)
        return get("{}{}".format(self.host, CLOSED_ONLY), headers=headers)

    def delete_api_key(self):
        """
        Deletes an API key
        Level 2 Auth required
        """
        self.assert_level_2_auth()

        request_args = RequestArgs(method="DELETE", request_path=DELETE_API_KEY)
        headers = create_level_2_headers(self.signer, self.creds, request_args)
        return delete("{}{}".format(self.host, DELETE_API_KEY), headers=headers)

    def create_readonly_api_key(self) -> ReadonlyApiKeyResponse:
        """
        Creates a new readonly API key for a user
        Level 2 Auth required
        """
        self.assert_level_2_auth()

        request_args = RequestArgs(method="POST", request_path=CREATE_READONLY_API_KEY)
        headers = create_level_2_headers(self.signer, self.creds, request_args)

        response = post(
            "{}{}".format(self.host, CREATE_READONLY_API_KEY), headers=headers
        )
        try:
            return ReadonlyApiKeyResponse(api_key=response["apiKey"])
        except:
            self.logger.error("Couldn't parse readonly API key response")
            return None

    def get_readonly_api_keys(self) -> list[str]:
        """
        Gets the available readonly API keys for this address
        Level 2 Auth required
        """
        self.assert_level_2_auth()

        request_args = RequestArgs(method="GET", request_path=GET_READONLY_API_KEYS)
        headers = create_level_2_headers(self.signer, self.creds, request_args)
        return get("{}{}".format(self.host, GET_READONLY_API_KEYS), headers=headers)

    def delete_readonly_api_key(self, key: str) -> bool:
        """
        Deletes a readonly API key for a user
        Level 2 Auth required
        """
        self.assert_level_2_auth()

        body = {"key": key}
        serialized = json.dumps(body, separators=(",", ":"), ensure_ascii=False)
        request_args = RequestArgs(
            method="DELETE",
            request_path=DELETE_READONLY_API_KEY,
            body=body,
            serialized_body=serialized,
        )
        headers = create_level_2_headers(self.signer, self.creds, request_args)
        return delete(
            "{}{}".format(self.host, DELETE_READONLY_API_KEY),
            headers=headers,
            data=serialized,
        )

    def validate_readonly_api_key(self, address: str, key: str) -> str:
        """
        Validates a readonly API key for a given address
        This is a public endpoint, no authentication required
        """
        return get(
            "{}{}?address={}&key={}".format(
                self.host, VALIDATE_READONLY_API_KEY, address, key
            )
        )

    def get_midpoint(self, token_id):
        """
        Get the mid market price for the given market
        """
        return get("{}{}?token_id={}".format(self.host, MID_POINT, token_id))

    def get_midpoints(self, params: list[BookParams]):
        """
        Get the mid market prices for a set of token ids
        """
        body = [{"token_id": param.token_id} for param in params]
        return post("{}{}".format(self.host, MID_POINTS), data=body)

    def get_price(self, token_id, side):
        """
        Get the market price for the given market
        """
        return get("{}{}?token_id={}&side={}".format(self.host, PRICE, token_id, side))

    def get_prices(self, params: list[BookParams]):
        """
        Get the market prices for a set
        """
        body = [{"token_id": param.token_id, "side": param.side} for param in params]
        return post("{}{}".format(self.host, GET_PRICES), data=body)

    def get_spread(self, token_id):
        """
        Get the spread for the given market
        """
        return get("{}{}?token_id={}".format(self.host, GET_SPREAD, token_id))

    def get_spreads(self, params: list[BookParams]):
        """
        Get the spreads for a set of token ids
        """
        body = [{"token_id": param.token_id} for param in params]
        return post("{}{}".format(self.host, GET_SPREADS), data=body)

    def get_tick_size(self, token_id: str) -> TickSize:
        cached_at = self.__tick_size_timestamps.get(token_id)

        if (
            token_id in self.__tick_sizes
            and cached_at is not None
            and (time.monotonic() - cached_at) < self.__tick_size_ttl
        ):
            return self.__tick_sizes[token_id]

        if token_id in self.__token_condition_map:
            self.get_clob_market_info(self.__token_condition_map[token_id])
            if token_id in self.__tick_sizes:
                return self.__tick_sizes[token_id]

        result = get("{}{}?token_id={}".format(self.host, GET_TICK_SIZE, token_id))
        self.__tick_sizes[token_id] = str(result["minimum_tick_size"])
        self.__tick_size_timestamps[token_id] = time.monotonic()

        return self.__tick_sizes[token_id]

    def clear_tick_size_cache(self, token_id: str = None):
        """
        Clear the cached tick size for one market or for all markets.
        """
        if token_id is not None:
            self.__tick_sizes.pop(token_id, None)
            self.__tick_size_timestamps.pop(token_id, None)
            return

        self.__tick_sizes.clear()
        self.__tick_size_timestamps.clear()

    def _update_tick_size_from_order_book(self, book: OrderBookSummary):
        """
        Refresh the tick size cache from an orderbook response when available.
        """
        if book and book.asset_id and book.tick_size:
            self.__tick_sizes[book.asset_id] = str(book.tick_size)
            self.__tick_size_timestamps[book.asset_id] = time.monotonic()

    def get_neg_risk(self, token_id: str) -> bool:
        if token_id in self.__neg_risk:
            return self.__neg_risk[token_id]

        if token_id in self.__token_condition_map:
            self.get_clob_market_info(self.__token_condition_map[token_id])
            return self.__neg_risk[token_id]

        result = get("{}{}?token_id={}".format(self.host, GET_NEG_RISK, token_id))
        self.__neg_risk[token_id] = result["neg_risk"]

        return result["neg_risk"]

    def __resolve_tick_size(
        self, token_id: str, tick_size: TickSize = None
    ) -> TickSize:
        min_tick_size = self.get_tick_size(token_id)
        if tick_size is not None:
            if is_tick_size_smaller(tick_size, min_tick_size):
                raise Exception(
                    "invalid tick size ("
                    + str(tick_size)
                    + "), minimum for the market is "
                    + str(min_tick_size),
                )
        else:
            tick_size = min_tick_size
        return tick_size

    def create_order(
        self, order_args: OrderArgs, options: Optional[PartialCreateOrderOptions] = None
    ):
        """
        Creates and signs an order
        Level 1 Auth required
        """
        self.assert_level_1_auth()
        order_args = apply_site_order_context(order_args)

        # add resolve_order_options, or similar
        tick_size = self.__resolve_tick_size(
            order_args.token_id,
            options.tick_size if options else None,
        )

        if not price_valid(order_args.price, tick_size):
            raise Exception(
                "price ("
                + str(order_args.price)
                + "), min: "
                + str(tick_size)
                + " - max: "
                + str(1 - float(tick_size))
            )

        order_args.builder_code = builder_code_to_bytes32(order_args.builder_code)

        neg_risk = (
            options.neg_risk
            if options and options.neg_risk
            else self.get_neg_risk(order_args.token_id)
        )

        return self.builder.create_order(
            order_args,
            CreateOrderOptions(
                tick_size=tick_size,
                neg_risk=neg_risk,
            ),
        )

    def create_market_order(
        self,
        order_args: MarketOrderArgs,
        options: Optional[PartialCreateOrderOptions] = None,
    ):
        """
        Creates and signs an order
        Level 1 Auth required
        """
        self.assert_level_1_auth()
        order_args = apply_site_order_context(order_args)

        # add resolve_order_options, or similar
        tick_size = self.__resolve_tick_size(
            order_args.token_id,
            options.tick_size if options else None,
        )

        if order_args.price is None or order_args.price <= 0:
            order_args.price = self.calculate_market_price(
                order_args.token_id,
                order_args.side,
                order_args.amount,
                order_args.order_type,
            )

        if not price_valid(order_args.price, tick_size):
            raise Exception(
                "price ("
                + str(order_args.price)
                + "), min: "
                + str(tick_size)
                + " - max: "
                + str(1 - float(tick_size))
            )

        order_args.builder_code = builder_code_to_bytes32(order_args.builder_code)

        if order_args.side == "BUY" and getattr(order_args, "user_usdc_balance", 0):
            self.__ensure_market_info_cached(order_args.token_id)
            self.__ensure_builder_fee_rate_cached(order_args.builder_code)
            fee_info = self.__fee_infos.get(order_args.token_id, FeeInfo())
            builder_fee = self.__builder_fee_rates.get(
                order_args.builder_code, BuilderFeeRate()
            )
            order_args.amount = adjust_market_buy_amount_for_dynamic_fees(
                order_args.amount,
                order_args.price,
                order_args.user_usdc_balance,
                fee_info.rate,
                fee_info.exponent,
                builder_fee.taker_share,
            )

        neg_risk = (
            options.neg_risk
            if options and options.neg_risk
            else self.get_neg_risk(order_args.token_id)
        )

        return self.builder.create_market_order(
            order_args,
            CreateOrderOptions(
                tick_size=tick_size,
                neg_risk=neg_risk,
            ),
        )

    def post_orders(self, args: list[PostOrdersArgs]):
        """
        Posts orders
        """
        self.assert_level_2_auth()
        self._ensure_geoblock_allowed()
        body = [
            order_to_json(arg.order, self.creds.api_key, arg.orderType, arg.postOnly)
            for arg in args
        ]
        request_args = RequestArgs(
            method="POST",
            request_path=POST_ORDERS,
            body=body,
            serialized_body=json.dumps(body, separators=(",", ":"), ensure_ascii=False),
        )
        headers = create_level_2_headers(self.signer, self.creds, request_args)
        # Builder flow
        if self.can_builder_auth():
            builder_headers = self._generate_builder_headers(request_args, headers)
            if builder_headers is not None:
                return post(
                    "{}{}".format(self.host, POST_ORDERS),
                    headers=builder_headers,
                    data=request_args.serialized_body,
                )
        # send exact serialized bytes
        return post(
            "{}{}".format(self.host, POST_ORDERS),
            headers=headers,
            data=request_args.serialized_body,
        )

    def post_order(
        self, order, orderType: OrderType = OrderType.GTC, post_only: bool = False
    ):
        """
        Posts the order
        """
        if post_only and (orderType != OrderType.GTC and orderType != OrderType.GTD):
            raise Exception("post_only orders can only be of type GTC or GTD")

        self.assert_level_2_auth()
        self._ensure_geoblock_allowed()
        body = order_to_json(order, self.creds.api_key, orderType, post_only)
        request_args = RequestArgs(
            method="POST",
            request_path=POST_ORDER,
            body=body,
            serialized_body=json.dumps(body, separators=(",", ":"), ensure_ascii=False),
        )
        headers = create_level_2_headers(self.signer, self.creds, request_args)
        # Builder flow
        if self.can_builder_auth():
            builder_headers = self._generate_builder_headers(request_args, headers)
            if builder_headers is not None:
                return post(
                    "{}{}".format(self.host, POST_ORDER),
                    headers=builder_headers,
                    data=request_args.serialized_body,
                )
        return post(
            "{}{}".format(self.host, POST_ORDER),
            headers=headers,
            data=request_args.serialized_body,
        )

    def create_and_post_order(
        self, order_args: OrderArgs, options: PartialCreateOrderOptions = None
    ):
        """
        Utility function to create and publish an order
        """
        ord = self.create_order(order_args, options)
        return self.post_order(ord)

    def cancel(self, order_id):
        """
        Cancels an order
        Level 2 Auth required
        """
        self.assert_level_2_auth()
        body = {"orderID": order_id}

        request_args = RequestArgs(
            method="DELETE",
            request_path=CANCEL,
            body=body,
            serialized_body=json.dumps(body, separators=(",", ":"), ensure_ascii=False),
        )
        headers = create_level_2_headers(self.signer, self.creds, request_args)
        return delete(
            "{}{}".format(self.host, CANCEL),
            headers=headers,
            data=request_args.serialized_body,
        )

    def cancel_orders(self, order_ids):
        """
        Cancels orders
        Level 2 Auth required
        """
        self.assert_level_2_auth()
        body = order_ids
        serialized = json.dumps(body, separators=(",", ":"), ensure_ascii=False)
        request_args = RequestArgs(
            method="DELETE",
            request_path=CANCEL_ORDERS,
            body=body,
            serialized_body=serialized,
        )
        headers = create_level_2_headers(self.signer, self.creds, request_args)
        return delete(
            "{}{}".format(self.host, CANCEL_ORDERS), headers=headers, data=serialized
        )

    def cancel_all(self):
        """
        Cancels all available orders for the user
        Level 2 Auth required
        """
        self.assert_level_2_auth()
        request_args = RequestArgs(method="DELETE", request_path=CANCEL_ALL)
        headers = create_level_2_headers(self.signer, self.creds, request_args)
        return delete("{}{}".format(self.host, CANCEL_ALL), headers=headers)

    def post_heartbeat(self, heartbeat_id: Optional[str]):
        """
        Sends a heartbeat to the server, if heartbeats are started and one isn't sent within 10s, all orders will be cancelled
        Requires Level 2 authentication
        """
        self.assert_level_2_auth()
        body = {"heartbeat_id": heartbeat_id}
        serialized = json.dumps(body, separators=(",", ":"), ensure_ascii=False)
        request_args = RequestArgs(
            method="POST",
            request_path=POST_HEARTBEAT,
            body=body,
            serialized_body=serialized,
        )
        headers = create_level_2_headers(self.signer, self.creds, request_args)
        return post(
            "{}{}".format(self.host, POST_HEARTBEAT), headers=headers, data=serialized
        )

    def cancel_market_orders(self, market: str = "", asset_id: str = ""):
        """
        Cancels orders
        Level 2 Auth required
        """
        self.assert_level_2_auth()
        body = {"market": market, "asset_id": asset_id}
        serialized = json.dumps(body, separators=(",", ":"), ensure_ascii=False)
        request_args = RequestArgs(
            method="DELETE",
            request_path=CANCEL_MARKET_ORDERS,
            body=body,
            serialized_body=serialized,
        )
        headers = create_level_2_headers(self.signer, self.creds, request_args)
        return delete(
            "{}{}".format(self.host, CANCEL_MARKET_ORDERS),
            headers=headers,
            data=serialized,
        )

    def get_orders(self, params: OpenOrderParams = None, next_cursor="MA=="):
        """
        Gets orders for the API key
        Requires Level 2 authentication
        """
        self.assert_level_2_auth()
        request_args = RequestArgs(method="GET", request_path=ORDERS)
        headers = create_level_2_headers(self.signer, self.creds, request_args)

        results = []
        next_cursor = next_cursor if next_cursor is not None else "MA=="
        while next_cursor != END_CURSOR:
            url = add_query_open_orders_params(
                "{}{}".format(self.host, ORDERS), params, next_cursor
            )
            response = get(url, headers=headers)
            next_cursor = response["next_cursor"]
            results += response["data"]

        return results

    def get_order_book(self, token_id) -> OrderBookSummary:
        """
        Fetches the orderbook for the token_id
        """
        raw_obs = get("{}{}?token_id={}".format(self.host, GET_ORDER_BOOK, token_id))
        result = parse_raw_orderbook_summary(raw_obs)
        self._update_tick_size_from_order_book(result)
        return result

    def get_order_books(self, params: list[BookParams]) -> list[OrderBookSummary]:
        """
        Fetches the orderbook for a set of token ids
        """
        body = [{"token_id": param.token_id} for param in params]
        raw_obs = post("{}{}".format(self.host, GET_ORDER_BOOKS), data=body)
        results = [parse_raw_orderbook_summary(r) for r in raw_obs]
        for book in results:
            self._update_tick_size_from_order_book(book)
        return results

    def get_order_book_hash(self, orderbook: OrderBookSummary) -> str:
        """
        Calculates the hash for the given orderbook
        """
        return generate_orderbook_summary_hash(orderbook)

    def get_order(self, order_id):
        """
        Fetches the order corresponding to the order_id
        Requires Level 2 authentication
        """
        self.assert_level_2_auth()
        endpoint = "{}{}".format(GET_ORDER, order_id)
        request_args = RequestArgs(method="GET", request_path=endpoint)
        headers = create_level_2_headers(self.signer, self.creds, request_args)
        return get("{}{}".format(self.host, endpoint), headers=headers)

    def get_trades(self, params: TradeParams = None, next_cursor="MA=="):
        """
        Fetches the trade history for a user
        Requires Level 2 authentication
        """
        self.assert_level_2_auth()
        request_args = RequestArgs(method="GET", request_path=TRADES)
        headers = create_level_2_headers(self.signer, self.creds, request_args)

        results = []
        next_cursor = next_cursor if next_cursor is not None else "MA=="
        while next_cursor != END_CURSOR:
            url = add_query_trade_params(
                "{}{}".format(self.host, TRADES), params, next_cursor
            )
            response = get(url, headers=headers)
            next_cursor = response["next_cursor"]
            results += response["data"]

        return results

    def get_last_trade_price(self, token_id):
        """
        Fetches the last trade price token_id
        """
        return get("{}{}?token_id={}".format(self.host, GET_LAST_TRADE_PRICE, token_id))

    def get_last_trades_prices(self, params: list[BookParams]):
        """
        Fetches the last trades prices for a set of token ids
        """
        body = [{"token_id": param.token_id} for param in params]
        return post("{}{}".format(self.host, GET_LAST_TRADES_PRICES), data=body)

    def assert_level_1_auth(self):
        """
        Level 1 Poly Auth
        """
        if self.mode < L1:
            raise PolyException(L1_AUTH_UNAVAILABLE)

    def assert_level_2_auth(self):
        """
        Level 2 Poly Auth
        """
        if self.mode < L2:
            raise PolyException(L2_AUTH_UNAVAILABLE)

    def assert_builder_auth(self):
        """
        Builder Auth
        """
        if not self.can_builder_auth():
            raise PolyException(BUILDER_AUTH_UNAVAILABLE)

    def can_builder_auth(self) -> bool:
        return (
            SITE_CONFIG["builder_mode"]
            and self.builder_config is not None
            and self.builder_config.is_valid()
        )

    def _get_client_mode(self):
        if self.signer is not None and self.creds is not None:
            return L2
        if self.signer is not None:
            return L1
        return L0

    def _generate_builder_headers(self, request_args: RequestArgs, headers: dict):
        """
        Generates builder headers and attaches them to the L2 Header
        """
        if self.builder_config is not None:
            builder_headers = self._get_builder_headers(
                request_args.method,
                request_args.request_path,
                request_args.serialized_body,
            )
            if builder_headers is None:
                return None
            return enrich_l2_headers_with_builder_headers(headers, builder_headers)
        return None

    def _get_builder_headers(self, method: str, path: str, body: Optional[str] = None):
        """
        Generates builder headers for the given method, path, and body.

        Args:
            method (str): HTTP method.
            path (str): Request path.
            body (Optional[str]): Pre-serialized JSON string or None.

        Returns:
            dict or None: Builder headers as a dictionary, or None if not available.
        """
        headers = self.builder_config.generate_builder_headers(method, path, body)
        if headers:
            return headers.to_dict()
        return None

    def _ensure_geoblock_allowed(self):
        if not SITE_CONFIG["geoblock"]:
            return

        if self._geoblock_status is None:
            site_url = SITE_CONFIG["site_url"].strip()
            if not site_url:
                raise PolyException(
                    "site_url must be configured when geoblock is enabled"
                )

            self._geoblock_status = get(
                "{}/?url={}".format(GEOBLOCK_HOST, quote(site_url, safe=""))
            )

        if self._geoblock_status.get("blocked"):
            raise PolyException(
                "trading blocked for configured site_url ({}) in {}, {}".format(
                    SITE_CONFIG["site_url"],
                    self._geoblock_status.get("country", "unknown"),
                    self._geoblock_status.get("region", "unknown"),
                )
            )

    def get_notifications(self):
        """
        Fetches the notifications for a user
        Requires Level 2 authentication
        """
        self.assert_level_2_auth()
        request_args = RequestArgs(method="GET", request_path=GET_NOTIFICATIONS)
        headers = create_level_2_headers(self.signer, self.creds, request_args)
        url = "{}{}?signature_type={}".format(
            self.host, GET_NOTIFICATIONS, self.builder.sig_type
        )
        return get(url, headers=headers)

    def drop_notifications(self, params: DropNotificationParams = None):
        """
        Drops the notifications for a user
        Requires Level 2 authentication
        """
        self.assert_level_2_auth()
        request_args = RequestArgs(method="DELETE", request_path=DROP_NOTIFICATIONS)
        headers = create_level_2_headers(self.signer, self.creds, request_args)
        url = drop_notifications_query_params(
            "{}{}".format(self.host, DROP_NOTIFICATIONS), params
        )
        return delete(url, headers=headers)

    def get_balance_allowance(self, params: BalanceAllowanceParams = None):
        """
        Fetches the balance & allowance for a user
        Requires Level 2 authentication
        """
        self.assert_level_2_auth()
        request_args = RequestArgs(method="GET", request_path=GET_BALANCE_ALLOWANCE)
        headers = create_level_2_headers(self.signer, self.creds, request_args)
        if params.signature_type == -1:
            params.signature_type = self.builder.sig_type
        url = add_balance_allowance_params_to_url(
            "{}{}".format(self.host, GET_BALANCE_ALLOWANCE), params
        )
        return get(url, headers=headers)

    def update_balance_allowance(self, params: BalanceAllowanceParams = None):
        """
        Updates the balance & allowance for a user
        Requires Level 2 authentication
        """
        self.assert_level_2_auth()
        request_args = RequestArgs(method="GET", request_path=UPDATE_BALANCE_ALLOWANCE)
        headers = create_level_2_headers(self.signer, self.creds, request_args)
        if params.signature_type == -1:
            params.signature_type = self.builder.sig_type
        url = add_balance_allowance_params_to_url(
            "{}{}".format(self.host, UPDATE_BALANCE_ALLOWANCE), params
        )
        return get(url, headers=headers)

    def is_order_scoring(self, params: OrderScoringParams):
        """
        Check if the order is currently scoring
        Requires Level 2 authentication
        """
        self.assert_level_2_auth()
        request_args = RequestArgs(method="GET", request_path=IS_ORDER_SCORING)
        headers = create_level_2_headers(self.signer, self.creds, request_args)
        url = add_order_scoring_params_to_url(
            "{}{}".format(self.host, IS_ORDER_SCORING), params
        )
        return get(url, headers=headers)

    def are_orders_scoring(self, params: OrdersScoringParams):
        """
        Check if the orders are currently scoring
        Requires Level 2 authentication
        """
        self.assert_level_2_auth()
        body = params.orderIds
        serialized = json.dumps(body, separators=(",", ":"), ensure_ascii=False)
        request_args = RequestArgs(
            method="POST",
            request_path=ARE_ORDERS_SCORING,
            body=body,
            serialized_body=serialized,
        )
        headers = create_level_2_headers(self.signer, self.creds, request_args)
        return post(
            "{}{}".format(self.host, ARE_ORDERS_SCORING),
            headers=headers,
            data=serialized,
        )

    def get_sampling_markets(self, next_cursor="MA==") -> dict[str, Any]:
        """
        Get the current sampling markets
        """
        return self.__get_site_scoped_market_page(GET_SAMPLING_MARKETS, next_cursor)

    def get_sampling_simplified_markets(self, next_cursor="MA==") -> dict[str, Any]:
        """
        Get the current sampling simplified markets
        """
        return self.__get_site_scoped_market_page(
            GET_SAMPLING_SIMPLIFIED_MARKETS, next_cursor
        )

    def get_markets(self, next_cursor="MA==") -> dict[str, Any]:
        """
        Get the current markets
        """
        return self.__get_site_scoped_market_page(GET_MARKETS, next_cursor)

    def get_simplified_markets(self, next_cursor="MA==") -> dict[str, Any]:
        """
        Get the current simplified markets
        """
        return self.__get_site_scoped_market_page(GET_SIMPLIFIED_MARKETS, next_cursor)

    def get_market(self, condition_id: str) -> dict[str, Any]:
        """
        Get a market by condition_id
        """
        return get("{}{}{}".format(self.host, GET_MARKET, condition_id))

    def get_market_by_token(self, token_id: str) -> MarketByTokenResponse:
        """
        Get the parent market and mirror identifiers for a token.
        """
        return get("{}{}{}".format(self.host, GET_MARKETS_BY_TOKEN, token_id))

    def get_clob_market_info(self, condition_id: str) -> dict[str, Any]:
        """
        Get V2 CLOB market info and populate local fee/tick/neg-risk caches.
        Supports both compact (`c/t/mts/nr/fd`) and expanded Kuest response shapes.
        """
        result = get("{}{}{}".format(self.host, GET_CLOB_MARKET, condition_id))
        tokens = result.get("t") or result.get("tokens")
        if not tokens:
            raise PolyException(
                f"failed to fetch market info for condition id {condition_id}"
            )

        min_tick_size = result.get("mts") or result.get("min_tick_size")
        neg_risk = result.get("nr", result.get("neg_risk", False))
        fd = result.get("fd") or {}
        maker_rate_bps = int(fd.get("maker_fee_rate_bps") or 0)
        taker_rate_bps = int(fd.get("taker_fee_rate_bps") or 0)

        for token in tokens:
            if not token:
                continue
            token_id = token.get("t") or token.get("token_id")
            if not token_id:
                continue
            self.__token_condition_map[token_id] = (
                result.get("c") or result.get("condition_id") or condition_id
            )
            if min_tick_size is not None:
                self.__tick_sizes[token_id] = str(min_tick_size)
                self.__tick_size_timestamps[token_id] = time.monotonic()
            self.__neg_risk[token_id] = neg_risk
            self.__fee_infos[token_id] = FeeInfo(
                maker_rate_bps=maker_rate_bps,
                taker_rate_bps=taker_rate_bps,
                rate=float(fd.get("r") or 0),
                exponent=float(fd.get("e") or 0),
            )

        return result

    def get_market_trades_events(self, condition_id):
        """
        Get the market's trades events by condition id
        """
        return get("{}{}{}".format(self.host, GET_MARKET_TRADES_EVENTS, condition_id))

    def get_builder_trades(self, params: TradeParams = None, next_cursor="MA=="):
        """
        Get trades originated by the builder
        """
        self.assert_builder_auth()

        request_args = RequestArgs(method="GET", request_path=GET_BUILDER_TRADES)
        headers = self._get_builder_headers(
            request_args.method, request_args.request_path, request_args.body
        )

        results = []
        next_cursor = next_cursor if next_cursor is not None else "MA=="
        while next_cursor != END_CURSOR:
            url = add_query_trade_params(
                "{}{}".format(self.host, GET_BUILDER_TRADES), params, next_cursor
            )
            response = get(url, headers=headers)
            next_cursor = response["next_cursor"]
            results += response["data"]

        return results

    def get_builder_fee_rate(self, builder_code: str) -> BuilderFeeRate:
        """
        Get and cache the V2 builder fee rate for a builder wallet/code.
        """
        normalized_builder_code = builder_code_to_bytes32(builder_code)
        self.__ensure_builder_fee_rate_cached(normalized_builder_code)
        return self.__builder_fee_rates.get(normalized_builder_code, BuilderFeeRate())

    def calculate_market_price(
        self, token_id: str, side: str, amount: float, order_type: OrderType
    ) -> float:
        """
        Calculates the matching price considering an amount and the current orderbook
        """
        book = self.get_order_book(token_id)
        if book is None:
            raise Exception("no orderbook")
        if side == "BUY":
            if book.asks is None:
                raise Exception("no match")
            return self.builder.calculate_buy_market_price(
                book.asks, amount, order_type
            )
        else:
            if book.bids is None:
                raise Exception("no match")
            return self.builder.calculate_sell_market_price(
                book.bids, amount, order_type
            )

    def __ensure_builder_fee_rate_cached(self, builder_code: str):
        normalized_builder_code = builder_code_to_bytes32(builder_code)
        if normalized_builder_code in self.__builder_fee_rates:
            return

        result = get(
            "{}{}{}".format(self.host, GET_BUILDER_FEE_RATE, normalized_builder_code)
        )
        self.__builder_fee_rates[normalized_builder_code] = (
            parse_builder_fee_rate_response(result)
        )

    def __ensure_market_info_cached(self, token_id: str):
        if token_id in self.__fee_infos:
            return

        condition_id = self.__token_condition_map.get(token_id)
        if not condition_id:
            book = self.get_order_book(token_id)
            condition_id = book.market if book else None
            if not condition_id:
                raise PolyException(
                    f"failed to resolve condition id for token {token_id}"
                )
            self.__token_condition_map[token_id] = condition_id

        self.get_clob_market_info(condition_id)

    def __get_site_scoped_market_page(self, endpoint: str, next_cursor="MA=="):
        if not has_configured_site_scope():
            return get("{}{}?next_cursor={}".format(self.host, endpoint, next_cursor))

        cursor = next_cursor
        while True:
            response = get("{}{}?next_cursor={}".format(self.host, endpoint, cursor))
            data = response.get("data") if isinstance(response, dict) else []
            data = data if isinstance(data, list) else []
            scope = get_site_market_scope()
            filtered = filter_site_scoped_markets(data, scope)
            scoped_response = dict(response) if isinstance(response, dict) else {}
            scoped_response["data"] = filtered
            response_cursor = (
                response.get("next_cursor", END_CURSOR)
                if isinstance(response, dict)
                else END_CURSOR
            )

            if filtered or response_cursor == END_CURSOR or response_cursor == cursor:
                return scoped_response

            cursor = response_cursor

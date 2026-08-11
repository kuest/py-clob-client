from typing import Any
from dataclasses import dataclass, asdict
from json import dumps
from typing import Literal, Optional
from .constants import BYTES32_ZERO
from .order_utils.model.order_data_v2 import SignedOrderV2 as SignedOrder


class OrderType(enumerate):
    GTC = "GTC"
    FOK = "FOK"
    GTD = "GTD"
    FAK = "FAK"


@dataclass
class ApiCreds:
    api_key: str
    api_secret: str
    api_passphrase: str


@dataclass
class ReadonlyApiKeyResponse:
    api_key: str


@dataclass
class RequestArgs:
    method: str
    request_path: str
    body: Any = None
    serialized_body: Optional[str] = None


@dataclass
class BookParams:
    token_id: str
    side: str = ""


@dataclass
class OrderArgs:
    token_id: str
    """
    TokenID of the Conditional token asset being traded
    """

    price: float
    """
    Price used to create the order
    """

    size: float
    """
    Size in terms of the ConditionalToken
    """

    side: str
    """
    Side of the order
    """

    expiration: int = 0
    """
    Expiration timestamp kept offchain by the CLOB.
    """

    metadata: str = BYTES32_ZERO
    """
    Metadata bytes32 included in the signed order.
    """

    builder_code: str = BYTES32_ZERO
    """
    Builder code bytes32 included in the signed order.
    """


@dataclass
class MarketOrderArgs:
    token_id: str
    """
    TokenID of the Conditional token asset being traded
    """

    amount: float
    """
    BUY orders: $$$ Amount to buy
    SELL orders: Shares to sell
    """

    side: str
    """
    Side of the order
    """

    price: float = 0
    """
    Price used to create the order
    """

    order_type: OrderType = OrderType.FOK

    user_usdc_balance: float = 0
    """
    User USDC balance, used to adjust BUY market orders for total taker fees.
    """

    metadata: str = BYTES32_ZERO
    """
    Metadata bytes32 included in the signed order.
    """

    builder_code: str = BYTES32_ZERO
    """
    Builder code bytes32 included in the signed order.
    """


@dataclass
class TradeParams:
    id: str = None
    maker_address: str = None
    market: str = None
    asset_id: str = None
    before: int = None
    after: int = None


@dataclass
class OpenOrderParams:
    id: str = None
    market: str = None
    asset_id: str = None


@dataclass
class DropNotificationParams:
    ids: list[str] = None


@dataclass
class OrderSummary:
    price: str = None
    size: str = None

    @property
    def __dict__(self):
        return asdict(self)

    @property
    def json(self):
        return dumps(self.__dict__)


@dataclass
class OrderBookSummary:
    market: str = None
    asset_id: str = None
    timestamp: str = None
    bids: list[OrderSummary] = None
    asks: list[OrderSummary] = None
    min_order_size: str = None
    neg_risk: bool = None
    tick_size: str = None
    last_trade_price: str = None
    hash: str = None

    @property
    def __dict__(self):
        return asdict(self)

    @property
    def json(self):
        return dumps(self.__dict__, separators=(",", ":"))


class AssetType(enumerate):
    COLLATERAL = "COLLATERAL"
    CONDITIONAL = "CONDITIONAL"


@dataclass
class BalanceAllowanceParams:
    asset_type: AssetType = None
    token_id: str = None
    signature_type: int = 3


@dataclass
class OrderScoringParams:
    orderId: str


@dataclass
class OrdersScoringParams:
    orderIds: list[str]


TickSize = Literal["0.1", "0.01", "0.001", "0.0001"]


@dataclass
class CreateOrderOptions:
    tick_size: TickSize
    neg_risk: bool


@dataclass
class PartialCreateOrderOptions:
    tick_size: Optional[TickSize] = None
    neg_risk: Optional[bool] = None


@dataclass
class RoundConfig:
    price: float
    size: float
    amount: float


@dataclass
class FeeInfo:
    maker_rate_bps: int = 0
    taker_rate_bps: int = 0
    rate: float = 0.0
    exponent: float = 0.0


@dataclass
class BuilderFeeRate:
    maker_flat: int = 0
    taker_share: int = 3000


@dataclass
class BuilderTradeParams(TradeParams):
    builder_code: str = BYTES32_ZERO


@dataclass
class ContractConfig:
    """
    Contract Configuration
    """

    exchange: str
    """
    The exchange contract responsible for matching orders
    """

    collateral: str
    """
    The ERC20 token used as collateral for the exchange's markets
    """

    conditional_tokens: str
    """
    The ERC1155 conditional tokens contract
    """


@dataclass
class PostOrdersArgs:
    order: SignedOrder
    orderType: OrderType = OrderType.GTC
    postOnly: bool = False

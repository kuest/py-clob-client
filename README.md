<h1 align="center">
  <img src="https://github.com/user-attachments/assets/0cc687fb-89c4-43fa-a056-d89c307215ad" alt="Kuest" height="96" /><br/>
  Kuest Python CLOB Client
</h1>

[![PyPI](https://img.shields.io/pypi/v/kuest-py-clob-client.svg)](https://pypi.org/project/kuest-py-clob-client)
[![PR](https://github.com/kuest/py-clob-client/actions/workflows/pr.yml/badge.svg)](https://github.com/kuest/py-clob-client/actions/workflows/pr.yml)


## Installation

```bash
pip install kuest-py-clob-client
```

## Read-Only Usage

```python
from py_clob_client.client import ClobClient

client = ClobClient("https://clob.kuest.com")

print(client.get_ok())
print(client.get_server_time())
```

## Market mirrors

Market discovery responses expose optional mirror identifiers. The presence of
`mirror_condition_id` identifies a mirrored market; token mappings use
`mirror_token_id`, `mirror_primary_token_id`, and `mirror_secondary_token_id`.
The methods continue to return dictionaries, with `TypedDict` definitions
available from `py_clob_client.clob_types` and the package root.

```python
from py_clob_client import ClobClient

client = ClobClient("https://clob.kuest.com")
market = client.get_market_by_token("<token-id>")

if market.get("mirror_condition_id"):
    print(market["mirror_condition_id"])
    print(market.get("mirror_primary_token_id"))

clob_market = client.get_clob_market_info(market["condition_id"])
for token in clob_market.get("t", []):
    if token:
        print(token.get("mirror_token_id"))
```

## Wallet-Only Trading

Kuest trading uses Deposit Wallet orders only. The public order path defaults to `signature_type=3` and rejects signature types `0`, `1`, and `2`.

```python
from py_clob_client.client import ClobClient

HOST = "https://clob.kuest.com"
CHAIN_ID = 137
PRIVATE_KEY = "<owner-private-key>"
DEPOSIT_WALLET = "<deposit-wallet-address>"

client = ClobClient(
    HOST,
    chain_id=CHAIN_ID,
    key=PRIVATE_KEY,
    signature_type=3,
    funder=DEPOSIT_WALLET,
)
client.set_api_creds(client.create_or_derive_api_creds())
```

## Place a Limit Order

```python
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType
from py_clob_client.order_builder.constants import BUY

client = ClobClient(
    "https://clob.kuest.com",
    chain_id=137,
    key="<owner-private-key>",
    signature_type=3,
    funder="<deposit-wallet-address>",
)
client.set_api_creds(client.create_or_derive_api_creds())

order = OrderArgs(token_id="<token-id>", price=0.42, size=5.0, side=BUY)
signed = client.create_order(order)
response = client.post_order(signed, OrderType.GTC)
print(response)
```

## Place a Market Order

```python
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import MarketOrderArgs, OrderType
from py_clob_client.order_builder.constants import BUY

client = ClobClient(
    "https://clob.kuest.com",
    chain_id=137,
    key="<owner-private-key>",
    signature_type=3,
    funder="<deposit-wallet-address>",
)
client.set_api_creds(client.create_or_derive_api_creds())

order = MarketOrderArgs(token_id="<token-id>", amount=25.0, side=BUY, order_type=OrderType.FOK)
signed = client.create_market_order(order)
response = client.post_order(signed, OrderType.FOK)
print(response)
```

## Manage Orders

```python
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OpenOrderParams

client = ClobClient(
    "https://clob.kuest.com",
    chain_id=137,
    key="<owner-private-key>",
    signature_type=3,
    funder="<deposit-wallet-address>",
)
client.set_api_creds(client.create_or_derive_api_creds())

open_orders = client.get_orders(OpenOrderParams())
if open_orders:
    client.cancel(open_orders[0]["id"])

client.cancel_all()
```

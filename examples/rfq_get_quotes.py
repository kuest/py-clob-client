import os

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds
from py_clob_client.rfq import GetRfqQuotesParams
from py_clob_client.constants import POLYGON
from dotenv import load_dotenv

load_dotenv()


def main():
    host = os.getenv("CLOB_API_URL", "https://clob.kuest.com")
    chain_id = int(os.getenv("CHAIN_ID", POLYGON))
    key = os.getenv("PK")
    creds = ApiCreds(
        api_key=os.getenv("CLOB_API_KEY"),
        api_secret=os.getenv("CLOB_SECRET"),
        api_passphrase=os.getenv("CLOB_PASS_PHRASE"),
    )
    client = ClobClient(host, key=key, chain_id=chain_id, creds=creds)

    params = GetRfqQuotesParams(
        # quote_ids=["0197656d-56ee-74a4-a06a-3b179121f3bf"],
        state="active",
        # markets=["0x0000000000000000000000000000000000000000"],
        # size_min=5,
        # size_max=100,
        # price_min=0.1,
        # price_max=0.9,
        # sort_by="price",
        # sort_dir="asc",
        limit=10,
        # offset="MA==",
    )
    print("Requester quotes (quotes on my requests):")
    requester_resp = client.rfq.get_rfq_requester_quotes(params)
    print(requester_resp)

    print("\nQuoter quotes (quotes I've made):")
    quoter_resp = client.rfq.get_rfq_quoter_quotes(params)
    print(quoter_resp)

    print("Done!")


main()

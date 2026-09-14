import os

from dotenv import load_dotenv

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds
from py_clob_client.constants import POLYGON
from py_clob_client.rfq import GetRfqBestQuoteParams

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

    params = GetRfqBestQuoteParams(
        request_id=os.getenv("RFQ_REQUEST_ID", "replace-me-with-an-rfq-request-id")
    )
    resp = client.rfq.get_rfq_best_quote(params)
    print(resp)
    print("Done!")


main()

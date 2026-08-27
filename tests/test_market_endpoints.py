from unittest import TestCase
from unittest.mock import patch

from py_clob_client.client import ClobClient


class TestMarketEndpoints(TestCase):
    @patch("py_clob_client.client.get")
    def test_get_market_by_token_returns_mirror_identifiers(self, get):
        response = {
            "condition_id": "0xcondition",
            "mirror_condition_id": "0xmirror-condition",
            "primary_token_id": "token-1",
            "mirror_primary_token_id": "mirror-token-1",
            "secondary_token_id": "token-2",
            "mirror_secondary_token_id": "mirror-token-2",
        }
        get.return_value = response

        result = ClobClient("http://localhost").get_market_by_token("token-1")

        self.assertEqual(result, response)
        get.assert_called_once_with("http://localhost/markets-by-token/token-1")

import tempfile
import unittest
from pathlib import Path

from investement.brokers import ReadOnlySchwabClient, create_schwab_read_only_client


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
        self.checked = False

    def raise_for_status(self):
        self.checked = True

    def json(self):
        if not self.checked:
            raise AssertionError("status must be checked before reading JSON")
        return self.payload


class FakeSchwabClient:
    class Account:
        class Fields:
            POSITIONS = "positions"

    def __init__(self):
        self.last_fields = None

    def get_account_numbers(self):
        return FakeResponse([{"accountNumber": "masked", "hashValue": "hash"}])

    def get_accounts(self, fields=None):
        self.last_fields = fields
        return FakeResponse([{"securitiesAccount": {"positions": []}}])

    def get_account(self, account_hash, fields=None):
        self.last_fields = fields
        return FakeResponse({"hash": account_hash})

    def get_transactions(self, account_hash, **kwargs):
        return FakeResponse([])

    def get_quote(self, symbol):
        return FakeResponse({symbol: {"quote": {"lastPrice": 100}}})

    def get_quotes(self, symbols):
        return FakeResponse({symbol: {} for symbol in symbols})

    def get_price_history(self, symbol, **kwargs):
        return FakeResponse({"symbol": symbol, "candles": []})

    def place_order(self, *args, **kwargs):
        raise AssertionError("must never be reachable")


class SchwabReadOnlyTests(unittest.TestCase):
    def test_facade_exposes_reads_and_hides_order_capabilities(self):
        raw = FakeSchwabClient()
        client = ReadOnlySchwabClient(raw)
        self.assertEqual(client.account_numbers()[0]["hashValue"], "hash")
        client.accounts(include_positions=True)
        self.assertEqual(raw.last_fields, ["positions"])
        self.assertEqual(client.quote("aapl")["AAPL"]["quote"]["lastPrice"], 100)
        self.assertFalse(hasattr(client, "place_order"))
        self.assertFalse(hasattr(client, "cancel_order"))
        self.assertFalse(hasattr(client, "replace_order"))

    def test_token_file_inside_repository_is_rejected_before_auth(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaises(ValueError):
                create_schwab_read_only_client(
                    api_key="key",
                    app_secret="secret",
                    callback_url="https://127.0.0.1",
                    token_path=root / "schwab-token.json",
                    project_root=root,
                )


if __name__ == "__main__":
    unittest.main()

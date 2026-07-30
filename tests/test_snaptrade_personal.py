import base64
import hashlib
import hmac
import json
import unittest
from datetime import UTC, datetime
from unittest.mock import patch

from investement.agents import SnapTradeBrokerAgent
from investement.brokers import (
    ReadOnlySnapTradeClient,
    SnapTradeAPIError,
    SnapTradePersonalCredentials,
    sign_snaptrade_request,
)
from investement.cli.snaptrade_connect import (
    _keychain_write,
    connection_summary,
    portfolio_state_summary,
)


class FakeResponse:
    def __init__(self, payload, *, status_code=200, headers=None):
        self.payload = payload
        self.status_code = status_code
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("HTTP failure")

    def json(self):
        return self.payload


class FakeTransport:
    def __init__(self):
        self.urls = []

    def get(self, url, *, headers, timeout):
        self.urls.append(url)
        self.last_headers = headers
        self.last_timeout = timeout
        if url.split("?", 1)[0].endswith("/accounts"):
            return FakeResponse(
                [
                    {
                        "id": "account-private-id",
                        "number": "123456789",
                        "raw_type": "MARGIN",
                        "balance": {"total": {"amount": 80000, "currency": "USD"}},
                    }
                ]
            )
        if "/positions/all?" in url:
            return FakeResponse(
                {
                    "results": [
                        {
                            "instrument": {
                                "kind": "etf",
                                "symbol": "SPY",
                                "currency": "USD",
                            },
                            "units": 100,
                            "price": 600,
                            "currency": "USD",
                        }
                    ]
                }
            )
        if "/balances?" in url:
            return FakeResponse(
                [{"currency": {"code": "USD"}, "cash": 5000, "buying_power": 5000}]
            )
        raise AssertionError(f"unexpected URL: {url}")


class SnapTradePersonalTests(unittest.TestCase):
    def test_signature_uses_documented_canonical_payload(self):
        path = "/api/v1/accounts"
        query = "clientId=test-client&timestamp=123"
        expected_payload = json.dumps(
            {"content": None, "path": path, "query": query},
            separators=(",", ":"),
            sort_keys=True,
        )
        expected = base64.b64encode(
            hmac.new(b"secret", expected_payload.encode(), hashlib.sha256).digest()
        ).decode()
        self.assertEqual(sign_snaptrade_request(path, query, "secret"), expected)

    def test_read_only_client_fetches_accounts_positions_and_balances(self):
        transport = FakeTransport()
        client = ReadOnlySnapTradeClient(
            SnapTradePersonalCredentials("client", "consumer"),
            transport=transport,
            clock=lambda: 123,
        )
        portfolio = client.portfolio()
        self.assertEqual(len(portfolio), 1)
        self.assertEqual(len(portfolio[0]["positions"]), 1)
        self.assertEqual(len(portfolio[0]["balances"]), 1)
        self.assertTrue(all("userId=" not in url and "userSecret=" not in url for url in transport.urls))
        self.assertFalse(hasattr(client, "place_order"))
        self.assertFalse(hasattr(client, "cancel_order"))

    def test_agent_summary_redacts_account_identifiers(self):
        client = ReadOnlySnapTradeClient(
            SnapTradePersonalCredentials("client", "consumer"),
            transport=FakeTransport(),
            clock=lambda: 123,
        )
        snapshot = SnapTradeBrokerAgent(
            client,
            clock=lambda: datetime(2026, 7, 28, tzinfo=UTC),
        ).read_portfolio()
        summary = connection_summary(snapshot)
        rendered = str(summary)
        self.assertEqual(summary["status"], "connected")
        self.assertEqual(summary["accounts"][0]["positions"], 1)
        self.assertNotIn("123456789", rendered)
        self.assertNotIn("account-private-id", rendered)

    def test_agent_normalizes_current_portfolio_without_counting_unclassified_value(self):
        client = ReadOnlySnapTradeClient(
            SnapTradePersonalCredentials("client", "consumer"),
            transport=FakeTransport(),
            clock=lambda: 123,
        )
        state = SnapTradeBrokerAgent(
            client,
            clock=lambda: datetime(2026, 7, 28, tzinfo=UTC),
        ).current_portfolio("usd")
        self.assertEqual(state.base_currency, "USD")
        self.assertEqual(state.total_value, 80000)
        self.assertEqual(state.cash_value, 5000)
        self.assertAlmostEqual(state.current_weights["SPY"], 0.75)
        self.assertAlmostEqual(state.cash_weight, 0.0625)
        rendered = str(portfolio_state_summary(state))
        self.assertIn("SPY", rendered)
        self.assertNotIn("account-private-id", rendered)

    def test_credentials_repr_redacts_both_values(self):
        credentials = SnapTradePersonalCredentials("client-value", "consumer-value")
        self.assertNotIn("client-value", repr(credentials))
        self.assertNotIn("consumer-value", repr(credentials))

    def test_api_error_contains_safe_diagnostics_only(self):
        class RejectedTransport:
            def get(self, url, *, headers, timeout):
                return FakeResponse(
                    {"error_code": "INVALID_SIGNATURE", "message": "ignored"},
                    status_code=401,
                    headers={"x-request-id": "request-123"},
                )

        client = ReadOnlySnapTradeClient(
            SnapTradePersonalCredentials("client-private", "consumer-private"),
            transport=RejectedTransport(),
            clock=lambda: 123,
        )
        with self.assertRaises(SnapTradeAPIError) as raised:
            client.accounts()
        rendered = str(raised.exception)
        self.assertIn("status=401", rendered)
        self.assertIn("code=INVALID_SIGNATURE", rendered)
        self.assertIn("request_id=request-123", rendered)
        self.assertNotIn("client-private", rendered)
        self.assertNotIn("consumer-private", rendered)

    def test_rate_limit_retries_use_server_reset_header(self):
        class ThrottledTransport:
            def __init__(self):
                self.calls = 0

            def get(self, url, *, headers, timeout):
                self.calls += 1
                if self.calls == 1:
                    return FakeResponse(
                        {"code": "0000"},
                        status_code=429,
                        headers={"x-ratelimit-reset": "0.25"},
                    )
                return FakeResponse([])

        transport = ThrottledTransport()
        sleeps = []
        client = ReadOnlySnapTradeClient(
            SnapTradePersonalCredentials("client", "consumer"),
            transport=transport,
            clock=lambda: 123,
            sleeper=sleeps.append,
        )

        self.assertEqual(client.accounts(), ())
        self.assertEqual(transport.calls, 2)
        self.assertEqual(sleeps, [0.25])

    def test_client_rejects_non_snaptrade_or_insecure_base_urls(self):
        for base_url in ("http://api.snaptrade.com/api/v1", "https://example.com/api/v1"):
            with self.subTest(base_url=base_url), self.assertRaises(ValueError):
                ReadOnlySnapTradeClient(
                    SnapTradePersonalCredentials("client", "consumer"),
                    transport=FakeTransport(),
                    base_url=base_url,
                )

    @patch("investement.cli.snaptrade_connect.write_password")
    def test_keychain_write_uses_native_api(self, write_password):
        _keychain_write("service-name", "private-value")
        write_password.assert_called_once()
        self.assertEqual(write_password.call_args.args[1:], ("service-name", "private-value"))


if __name__ == "__main__":
    unittest.main()

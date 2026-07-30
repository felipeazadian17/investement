import base64
import hashlib
import hmac
import json
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import urlencode, urlparse

SNAPTRADE_BASE_URL = "https://api.snaptrade.com/api/v1"


class SnapTradeTransport(Protocol):
    def get(self, url: str, *, headers: Mapping[str, str], timeout: float) -> Any: ...


class SnapTradeAPIError(RuntimeError):
    def __init__(
        self,
        *,
        operation: str,
        status_code: int,
        error_code: str | None = None,
        request_id: str | None = None,
    ) -> None:
        self.operation = operation
        self.status_code = status_code
        self.error_code = error_code
        self.request_id = request_id
        details = [f"operation={operation}", f"status={status_code}"]
        if error_code:
            details.append(f"code={error_code}")
        if request_id:
            details.append(f"request_id={request_id}")
        super().__init__(", ".join(details))


@dataclass(frozen=True)
class SnapTradePersonalCredentials:
    client_id: str = field(repr=False)
    consumer_key: str = field(repr=False)

    def __post_init__(self) -> None:
        if not self.client_id.strip() or not self.consumer_key.strip():
            raise ValueError("SnapTrade client_id and consumer_key are required")


class ReadOnlySnapTradeClient:
    """Personal SnapTrade facade intentionally limited to portfolio reads."""

    def __init__(
        self,
        credentials: SnapTradePersonalCredentials,
        *,
        transport: SnapTradeTransport | None = None,
        clock: Callable[[], float] = time.time,
        base_url: str = SNAPTRADE_BASE_URL,
        timeout: float = 30.0,
        max_rate_limit_retries: int = 2,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        parsed_url = urlparse(base_url)
        if (
            parsed_url.scheme != "https"
            or parsed_url.hostname != "api.snaptrade.com"
            or parsed_url.username is not None
            or parsed_url.password is not None
            or parsed_url.query
            or parsed_url.fragment
        ):
            raise ValueError("SnapTrade base_url must be https://api.snaptrade.com")
        if not 0 < timeout <= 120:
            raise ValueError("SnapTrade timeout must be between zero and 120 seconds")
        if not 0 <= max_rate_limit_retries <= 5:
            raise ValueError("max_rate_limit_retries must be between zero and five")
        self.__credentials = credentials
        self.__transport = transport or _httpx_client()
        self.__clock = clock
        self.__base_url = base_url.rstrip("/")
        self.__timeout = timeout
        self.__max_rate_limit_retries = max_rate_limit_retries
        self.__sleeper = sleeper

    def accounts(self) -> Sequence[Mapping[str, Any]]:
        payload = self._get("/accounts")
        return _mapping_sequence(payload, "accounts")

    def positions(self, account_id: str) -> Sequence[Mapping[str, Any]]:
        payload = self._get(f"/accounts/{_required(account_id, 'account_id')}/positions/all")
        if isinstance(payload, Mapping):
            payload = payload.get("results", ())
        return _mapping_sequence(payload, "positions")

    def balances(self, account_id: str) -> Sequence[Mapping[str, Any]]:
        payload = self._get(f"/accounts/{_required(account_id, 'account_id')}/balances")
        return _mapping_sequence(payload, "balances")

    def portfolio(self, include_positions: bool = True) -> Sequence[Mapping[str, Any]]:
        result: list[Mapping[str, Any]] = []
        for account in self.accounts():
            account_id = str(account.get("id", "")).strip()
            if not account_id:
                raise ValueError("SnapTrade account response is missing id")
            result.append(
                {
                    "account": account,
                    "positions": tuple(self.positions(account_id)) if include_positions else (),
                    "balances": tuple(self.balances(account_id)),
                }
            )
        return tuple(result)

    def _get(self, resource: str) -> Any:
        path = f"/api/v1{resource}"
        response = None
        for attempt in range(self.__max_rate_limit_retries + 1):
            query = urlencode(
                {
                    "clientId": self.__credentials.client_id,
                    "timestamp": int(self.__clock()),
                }
            )
            signature = sign_snaptrade_request(
                path=path,
                query=query,
                consumer_key=self.__credentials.consumer_key,
            )
            response = self.__transport.get(
                f"{self.__base_url}{resource}?{query}",
                headers={"Accept": "application/json", "Signature": signature},
                timeout=self.__timeout,
            )
            if int(getattr(response, "status_code", 0)) != 429:
                break
            if attempt < self.__max_rate_limit_retries:
                self.__sleeper(_retry_delay(response, attempt))
        if response is None:
            raise RuntimeError("SnapTrade request produced no response")
        try:
            response.raise_for_status()
        except Exception as exc:
            raise _response_error(response, resource) from exc
        return response.json()


def sign_snaptrade_request(path: str, query: str, consumer_key: str) -> str:
    if not path.startswith("/api/v1/"):
        raise ValueError("SnapTrade signature path must start with /api/v1/")
    if not query or not consumer_key:
        raise ValueError("SnapTrade signature query and consumer key are required")
    canonical = json.dumps(
        {"content": None, "path": path, "query": query},
        separators=(",", ":"),
        sort_keys=True,
    )
    digest = hmac.new(
        consumer_key.encode("utf-8"),
        canonical.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return base64.b64encode(digest).decode("ascii")


def _httpx_client() -> SnapTradeTransport:
    try:
        import httpx
    except ImportError as exc:
        raise RuntimeError(
            "httpx is optional; install with `pip install -e '.[snaptrade]'`"
        ) from exc
    return httpx.Client()


def _mapping_sequence(payload: Any, label: str) -> Sequence[Mapping[str, Any]]:
    if not isinstance(payload, Sequence) or isinstance(payload, (str, bytes)):
        raise TypeError(f"SnapTrade {label} response must be a list")
    if any(not isinstance(item, Mapping) for item in payload):
        raise TypeError(f"SnapTrade {label} response contains an invalid item")
    return tuple(payload)


def _required(value: str, label: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{label} is required")
    if "/" in cleaned or "?" in cleaned:
        raise ValueError(f"{label} contains invalid characters")
    return cleaned


def _response_error(response: Any, resource: str) -> SnapTradeAPIError:
    headers = getattr(response, "headers", {})
    request_id = None
    if isinstance(headers, Mapping):
        request_id = headers.get("x-request-id") or headers.get("request-id")
    error_code = None
    try:
        payload = response.json()
    except Exception:  # noqa: BLE001 - diagnostics must tolerate non-JSON failures.
        payload = None
    if isinstance(payload, Mapping):
        value = payload.get("error_code") or payload.get("errorCode") or payload.get("code")
        if isinstance(value, (str, int)):
            error_code = str(value)
    operation = resource.strip("/").replace("/", ".") or "status"
    return SnapTradeAPIError(
        operation=operation,
        status_code=int(getattr(response, "status_code", 0)),
        error_code=error_code,
        request_id=str(request_id) if request_id else None,
    )


def _retry_delay(response: Any, attempt: int) -> float:
    headers = getattr(response, "headers", {})
    if isinstance(headers, Mapping):
        for name in (
            "x-ratelimit-account-reset",
            "x-ratelimit-reset",
            "retry-after",
        ):
            value = headers.get(name) or headers.get(name.title())
            try:
                if value is not None:
                    return min(max(float(value), 0.0), 60.0)
            except (TypeError, ValueError):
                pass
    return min(2.0**attempt, 60.0)

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


class ReadOnlySchwabClient:
    """Capability-restricted facade over schwab-py.

    The facade intentionally has no order placement, replacement, cancellation,
    preview, or streaming methods.
    """

    def __init__(self, client: Any) -> None:
        required = ("get_account_numbers", "get_accounts", "get_account", "get_transactions")
        missing = [name for name in required if not callable(getattr(client, name, None))]
        if missing:
            raise TypeError(f"Schwab client lacks read methods: {', '.join(missing)}")
        self.__client = client

    def account_numbers(self) -> Sequence[Mapping[str, Any]]:
        return _json(self.__client.get_account_numbers())

    def accounts(self, include_positions: bool = True) -> Sequence[Mapping[str, Any]]:
        fields = self._account_fields(include_positions)
        return _json(self.__client.get_accounts(fields=fields))

    def account(self, account_hash: str, include_positions: bool = True) -> Mapping[str, Any]:
        if not account_hash.strip():
            raise ValueError("account_hash is required")
        fields = self._account_fields(include_positions)
        return _json(self.__client.get_account(account_hash, fields=fields))

    def transactions(
        self,
        account_hash: str,
        start_date: Any,
        end_date: Any,
        transaction_types: Any,
        symbol: str | None = None,
    ) -> Sequence[Mapping[str, Any]]:
        if not account_hash.strip():
            raise ValueError("account_hash is required")
        return _json(
            self.__client.get_transactions(
                account_hash,
                start_date=start_date,
                end_date=end_date,
                transaction_types=transaction_types,
                symbol=symbol,
            )
        )

    def quote(self, symbol: str) -> Mapping[str, Any]:
        method = getattr(self.__client, "get_quote", None)
        if not callable(method):
            raise NotImplementedError("the underlying client does not expose get_quote")
        if not symbol.strip():
            raise ValueError("symbol is required")
        return _json(method(symbol.upper()))

    def quotes(self, symbols: Sequence[str]) -> Mapping[str, Any]:
        method = getattr(self.__client, "get_quotes", None)
        if not callable(method):
            raise NotImplementedError("the underlying client does not expose get_quotes")
        cleaned = tuple(symbol.strip().upper() for symbol in symbols if symbol.strip())
        if not cleaned:
            raise ValueError("at least one symbol is required")
        return _json(method(cleaned))

    def price_history(self, symbol: str, **kwargs: Any) -> Mapping[str, Any]:
        method = getattr(self.__client, "get_price_history", None)
        if not callable(method):
            raise NotImplementedError("the underlying client does not expose get_price_history")
        if not symbol.strip():
            raise ValueError("symbol is required")
        return _json(method(symbol.upper(), **kwargs))

    def _account_fields(self, include_positions: bool) -> list | None:
        if not include_positions:
            return None
        try:
            return [self.__client.Account.Fields.POSITIONS]
        except AttributeError as exc:
            raise RuntimeError("schwab-py Account.Fields.POSITIONS is unavailable") from exc


def create_schwab_read_only_client(
    api_key: str,
    app_secret: str,
    callback_url: str,
    token_path: Path,
    project_root: Path | None = None,
    **auth_kwargs: Any,
) -> ReadOnlySchwabClient:
    token = Path(token_path).expanduser().resolve()
    root = Path(project_root).resolve() if project_root is not None else Path.cwd().resolve()
    if _is_within(token, root):
        raise ValueError("store Schwab OAuth tokens outside the project repository")
    token.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if token.exists():
        token.chmod(0o600)
    try:
        from schwab.auth import easy_client
    except ImportError as exc:
        raise RuntimeError(
            "schwab-py is optional; install with `pip install -e '.[schwab]'`"
        ) from exc
    client = easy_client(
        api_key=api_key,
        app_secret=app_secret,
        callback_url=callback_url,
        token_path=str(token),
        **auth_kwargs,
    )
    if token.exists():
        token.chmod(0o600)
    return ReadOnlySchwabClient(client)


def _json(response: Any) -> Any:
    response.raise_for_status()
    return response.json()


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False

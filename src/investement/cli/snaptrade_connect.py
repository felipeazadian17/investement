import argparse
import getpass
import json
import os
import sys
from collections.abc import Mapping, Sequence
from typing import Any

from investement.agents import SnapTradeBrokerAgent
from investement.agents.models import BrokerAccountSnapshot, BrokerPortfolioState
from investement.brokers import (
    ReadOnlySnapTradeClient,
    SnapTradeAPIError,
    SnapTradePersonalCredentials,
)
from investement.cli.macos_keychain import (
    KeychainError,
    delete_password,
    read_password,
    write_password,
)

KEYCHAIN_CLIENT_ID_SERVICE = "investement.snaptrade.client-id"
KEYCHAIN_CONSUMER_KEY_SERVICE = "investement.snaptrade.consumer-key"


def load_credentials(*, interactive: bool = True) -> SnapTradePersonalCredentials:
    client_id = os.environ.get("SNAPTRADE_CLIENT_ID", "").strip()
    consumer_key = os.environ.get("SNAPTRADE_CONSUMER_KEY", "").strip()

    if sys.platform == "darwin":
        client_id = client_id or _keychain_read(KEYCHAIN_CLIENT_ID_SERVICE)
        consumer_key = consumer_key or _keychain_read(KEYCHAIN_CONSUMER_KEY_SERVICE)

    if interactive:
        client_id = client_id or getpass.getpass("SnapTrade Personal clientId: ").strip()
        consumer_key = consumer_key or getpass.getpass(
            "SnapTrade Personal consumerKey: "
        ).strip()

    if not client_id or not consumer_key:
        raise ValueError("faltan SNAPTRADE_CLIENT_ID y/o SNAPTRADE_CONSUMER_KEY")

    return SnapTradePersonalCredentials(client_id, consumer_key)


def connection_summary(snapshot: BrokerAccountSnapshot) -> dict[str, Any]:
    accounts = [_account_summary(index, item) for index, item in enumerate(snapshot.accounts, 1)]
    return {
        "status": "connected",
        "provider": "snaptrade-personal",
        "mode": "read-only",
        "retrieved_at": snapshot.retrieved_at.isoformat(),
        "account_count": len(accounts),
        "accounts": accounts,
    }


def portfolio_state_summary(state: BrokerPortfolioState) -> dict[str, Any]:
    return {
        "status": "connected",
        "provider": state.provider,
        "mode": "read-only",
        "retrieved_at": state.retrieved_at.isoformat(),
        "base_currency": state.base_currency,
        "total_value": state.total_value,
        "cash_value": state.cash_value,
        "cash_weight": state.cash_weight,
        "position_values": state.position_values,
        "current_weights": state.current_weights,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Conecta SnapTrade Personal al agente sin exponer ordenes."
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Lee las credenciales del entorno o del Keychain sin solicitarlas.",
    )
    parser.add_argument(
        "--reset-credentials",
        action="store_true",
        help="Elimina solamente las credenciales SnapTrade del Keychain y vuelve a pedirlas.",
    )
    parser.add_argument(
        "--show-portfolio-state",
        action="store_true",
        help="Muestra valores y pesos normalizados, sin IDs de cuenta.",
    )
    parser.add_argument(
        "--base-currency",
        default="USD",
        help="Moneda base para validar el portfolio normalizado (default: USD).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.reset_credentials:
        if sys.platform != "darwin":
            print("--reset-credentials requiere macOS Keychain.", file=sys.stderr)
            return 2
        _keychain_delete(KEYCHAIN_CLIENT_ID_SERVICE)
        _keychain_delete(KEYCHAIN_CONSUMER_KEY_SERVICE)
    try:
        credentials = load_credentials(interactive=not args.non_interactive)
    except (ValueError, RuntimeError) as exc:
        print(f"Configuracion de SnapTrade invalida: {exc}", file=sys.stderr)
        return 2

    try:
        agent = SnapTradeBrokerAgent(ReadOnlySnapTradeClient(credentials))
        if args.show_portfolio_state:
            output = portfolio_state_summary(agent.current_portfolio(args.base_currency))
        else:
            output = connection_summary(agent.read_portfolio())
    except SnapTradeAPIError as exc:
        print(f"SnapTrade rechazo la lectura: {exc}", file=sys.stderr)
        if exc.status_code == 401 and exc.error_code == "1083":
            print(
                "SnapTrade no valido el par Personal clientId/consumerKey. "
                "Comprueba que no esten invertidos y que la key sea Personal, no Commercial.",
                file=sys.stderr,
            )
        return 1
    except Exception as exc:  # noqa: BLE001 - do not leak signed request details.
        print(
            "No se pudo leer la cuenta de SnapTrade "
            f"({type(exc).__name__}). Revisa la Personal API Key y la conexion del broker.",
            file=sys.stderr,
        )
        return 1
    if not args.non_interactive and sys.platform == "darwin":
        try:
            _keychain_write(KEYCHAIN_CLIENT_ID_SERVICE, credentials.client_id)
            _keychain_write(KEYCHAIN_CONSUMER_KEY_SERVICE, credentials.consumer_key)
        except RuntimeError as exc:
            print(f"La conexion funciona, pero Keychain fallo: {exc}", file=sys.stderr)
            return 2
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


def _account_summary(index: int, payload: Mapping[str, Any]) -> dict[str, Any]:
    account = payload.get("account", {})
    positions = payload.get("positions", ())
    balances = payload.get("balances", ())
    summary: dict[str, Any] = {
        "label": f"account-{index}",
        "positions": len(positions) if isinstance(positions, Sequence) else 0,
    }
    if isinstance(account, Mapping):
        summary["type"] = account.get("raw_type") or account.get("account_category") or "unknown"
        total = account.get("balance", {})
        if isinstance(total, Mapping):
            total = total.get("total", {})
        if isinstance(total, Mapping) and "amount" in total:
            summary["total_value"] = {
                "amount": total["amount"],
                "currency": total.get("currency", "unknown"),
            }
    summary["balances"] = _balance_summary(balances)
    return summary


def _balance_summary(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, Sequence) or isinstance(payload, (str, bytes)):
        return []
    result = []
    for item in payload:
        if not isinstance(item, Mapping):
            continue
        currency = item.get("currency", {})
        code = currency.get("code", "unknown") if isinstance(currency, Mapping) else "unknown"
        result.append(
            {
                "currency": code,
                "cash": item.get("cash"),
                "buying_power": item.get("buying_power"),
            }
        )
    return result


def _keychain_read(service: str) -> str:
    try:
        return read_password(_keychain_account(), service).strip()
    except (KeychainError, OSError):
        return ""


def _keychain_write(service: str, value: str) -> None:
    try:
        write_password(_keychain_account(), service, value)
    except (KeychainError, OSError) as exc:
        raise RuntimeError(
            "no se pudo guardar la credencial en el Keychain de macOS"
        ) from exc


def _keychain_delete(service: str) -> None:
    try:
        delete_password(_keychain_account(), service)
    except (KeychainError, OSError):
        return


def _keychain_account() -> str:
    return os.environ.get("USER", "investement-local")


if __name__ == "__main__":
    raise SystemExit(main())

import argparse
import html
import io
import json
import math
import os
import statistics
import tempfile
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, replace
from datetime import UTC, date, datetime
from datetime import time as datetime_time
from itertools import pairwise
from pathlib import Path

import pandas as pd
import requests

from investement.agents import (
    AssetDataRequest,
    AuditorAgent,
    DataAgent,
    InvestorProfileAgent,
    InvestorProfileRequest,
    PortfolioConstructionAgent,
    PortfolioConstructionInputs,
    RiskAgent,
    RiskTolerance,
    TechnicalAgent,
    TechnicalParameters,
)
from investement.domain import DataProvenance, PriceBar, SignalAction
from investement.orchestration import (
    AgentFinding,
    EvidenceReference,
    InvestmentCommittee,
    JsonlAuditLog,
    JsonMemoryStore,
)
from investement.portfolio import AssetMetadata
from investement.valuation import ComparableObservation

UNIVERSE_REVISION = 1361794875
UNIVERSE_URL = (
    "https://en.wikipedia.org/w/index.php?"
    f"title=List_of_S%26P_500_companies&oldid={UNIVERSE_REVISION}"
)
RECOMMENDATION_DATE = date(2026, 7, 1)
EVALUATION_DATE = date(2026, 7, 27)
FUNDAMENTAL_PERIOD_CUTOFF = date(2026, 3, 31)
PRICE_START = date(2025, 1, 1)
PRICE_END_EXCLUSIVE = date(2026, 7, 28)
TERMINAL_GROWTH = 0.025
SHARE_EQUIVALENT_MULTIPLIERS = {"BRK.B": 1_500.0}
USER_AGENT = "InvestementResearch/0.1 (https://github.com/felipeazadian17/investement)"
YAHOO_TYPES = (
    "quarterlyFreeCashFlow",
    "quarterlyOperatingCashFlow",
    "quarterlyCapitalExpenditure",
    "quarterlyTotalRevenue",
    "quarterlyEBIT",
    "quarterlyTaxProvision",
    "quarterlyPretaxIncome",
    "quarterlyDilutedAverageShares",
    "quarterlyNetIncome",
    "quarterlyTotalDebt",
    "quarterlyCashCashEquivalentsAndShortTermInvestments",
    "quarterlyStockholdersEquity",
    "quarterlyOrdinarySharesNumber",
    "quarterlyNetDebt",
)
SECTOR_WACC = {
    "Communication Services": 0.09,
    "Consumer Discretionary": 0.09,
    "Consumer Staples": 0.075,
    "Energy": 0.10,
    "Financials": 0.09,
    "Health Care": 0.09,
    "Industrials": 0.085,
    "Information Technology": 0.10,
    "Materials": 0.09,
    "Real Estate": 0.08,
    "Utilities": 0.065,
}


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("resultados/sp500_2026-07-01"),
    )
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--refresh", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = args.output_dir / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    universe = load_universe(cache_dir, args.refresh)
    if args.limit is not None:
        universe = universe[: args.limit]
    print(f"Universe fixed at revision {UNIVERSE_REVISION}: {len(universe)} securities", flush=True)
    raw = fetch_all(universe, cache_dir, args.workers, args.refresh)
    benchmark_raw = fetch_company(
        {"index_symbol": "SPY", "yahoo_symbol": "SPY"},
        cache_dir,
        args.refresh,
        include_fundamentals=False,
    )
    rows, summary = run_models(universe, raw, benchmark_raw)
    audit_path = args.output_dir / "audit.jsonl"
    audit_path.unlink(missing_ok=True)
    auditor = AuditorAgent(
        JsonlAuditLog(audit_path),
        JsonMemoryStore(args.output_dir / "memory"),
    )
    receipt = auditor.record(
        f"sp500-{RECOMMENDATION_DATE.isoformat()}",
        "sp500-backtest.completed",
        {"summary": summary, "result_count": len(rows)},
        memory_key=f"sp500.{RECOMMENDATION_DATE.isoformat()}",
    )
    summary["audit"] = asdict(receipt)
    write_outputs(args.output_dir, rows, summary)
    print(json.dumps(summary, indent=2, sort_keys=True), flush=True)


def load_universe(cache_dir: Path, refresh: bool):
    path = cache_dir / f"sp500_wikipedia_oldid_{UNIVERSE_REVISION}.html"
    if refresh or not path.exists():
        response = request_with_retry(UNIVERSE_URL)
        atomic_write(path, response.text)
    tables = pd.read_html(io.StringIO(path.read_text(encoding="utf-8")))
    table = tables[0]
    universe = []
    for item in table.to_dict("records"):
        index_symbol = str(item["Symbol"]).strip()
        universe.append(
            {
                "index_symbol": index_symbol,
                "yahoo_symbol": index_symbol.replace(".", "-"),
                "company": str(item["Security"]).strip(),
                "sector": str(item["GICS Sector"]).strip(),
                "sub_industry": str(item["GICS Sub-Industry"]).strip(),
                "headquarters": str(item["Headquarters Location"]).strip(),
                "cik": str(item["CIK"]).zfill(10),
            }
        )
    return universe


def fetch_all(universe, cache_dir: Path, workers: int, refresh: bool):
    results = {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(fetch_company, item, cache_dir, refresh): item for item in universe
        }
        for completed, future in enumerate(as_completed(futures), start=1):
            item = futures[future]
            try:
                results[item["index_symbol"]] = future.result()
            except Exception as exc:  # noqa: BLE001 - isolate failures by security
                results[item["index_symbol"]] = {
                    "prices": None,
                    "fundamentals": None,
                    "errors": [f"worker: {type(exc).__name__}: {exc}"],
                }
            if completed % 25 == 0 or completed == len(futures):
                print(f"Fetched {completed}/{len(futures)}", flush=True)
    return results


def fetch_company(item, cache_dir: Path, refresh: bool, include_fundamentals: bool = True):
    symbol = item["yahoo_symbol"]
    errors = []
    prices = None
    fundamentals = None
    try:
        prices = cached_json(
            cache_dir / f"{symbol}_prices.json",
            f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
            {
                "period1": epoch(PRICE_START),
                "period2": epoch(PRICE_END_EXCLUSIVE),
                "interval": "1d",
                "events": "div,splits",
                "includeAdjustedClose": "true",
            },
            refresh,
        )
    except Exception as exc:  # noqa: BLE001 - preserve partial market-data coverage
        errors.append(f"prices: {type(exc).__name__}: {exc}")
    if include_fundamentals:
        try:
            fundamentals = cached_json(
                cache_dir / f"{symbol}_fundamentals.json",
                (
                    "https://query2.finance.yahoo.com/ws/fundamentals-timeseries/"
                    f"v1/finance/timeseries/{symbol}"
                ),
                {
                    "symbol": symbol,
                    "type": ",".join(YAHOO_TYPES),
                    "period1": epoch(date(2024, 1, 1)),
                    "period2": epoch(PRICE_END_EXCLUSIVE),
                },
                refresh,
            )
        except Exception as exc:  # noqa: BLE001 - preserve partial market-data coverage
            errors.append(f"fundamentals: {type(exc).__name__}: {exc}")
    return {"prices": prices, "fundamentals": fundamentals, "errors": errors}


def cached_json(path: Path, url: str, params: dict, refresh: bool):
    if not refresh and path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    response = request_with_retry(url, params)
    payload = response.json()
    atomic_write(path, json.dumps(payload, separators=(",", ":")))
    return payload


def request_with_retry(url: str, params: dict | None = None):
    last_error = None
    for attempt in range(5):
        try:
            response = requests.get(
                url,
                params=params,
                headers={"User-Agent": USER_AGENT},
                timeout=35,
            )
            if response.status_code == 429 or response.status_code >= 500:
                raise RuntimeError(f"HTTP {response.status_code}")
            response.raise_for_status()
            return response
        except Exception as exc:  # noqa: BLE001 - retry all transport/HTTP decode failures
            last_error = exc
            if attempt < 4:
                time.sleep(1.5 * (2**attempt))
    raise RuntimeError(f"request failed after retries: {last_error}")


def run_models(universe, raw, benchmark_raw):
    retrieved_at = datetime.now(UTC)
    prepared = {}
    for item in universe:
        symbol = item["index_symbol"]
        source = raw[symbol]
        prepared[symbol] = {
            "item": item,
            "bars": parse_price_bars(source.get("prices"), item["yahoo_symbol"], retrieved_at),
            "fundamentals": parse_fundamentals(source.get("fundamentals"), item["sector"], symbol),
            "errors": list(source.get("errors", [])),
        }

    data_agent = DataAgent(PreparedMarketData(prepared), clock=lambda: retrieved_at)
    profile = build_profile(universe)
    technical_parameters = TechnicalParameters()
    technical_agent = TechnicalAgent(technical_parameters)
    risk_agent = RiskAgent()
    committee = InvestmentCommittee()
    decisions = {}
    rows = []

    for item in universe:
        symbol = item["index_symbol"]
        company = prepared[symbol]
        bars = tuple(bar for bar in company["bars"] if bar.timestamp.date() <= RECOMMENDATION_DATE)
        evaluation_bars = tuple(
            bar for bar in company["bars"] if bar.timestamp.date() <= EVALUATION_DATE
        )
        row = base_row(item, company["errors"])
        if not bars or not evaluation_bars:
            row["data_status"] = "missing price history"
            rows.append(row)
            continue
        start_bar = bars[-1]
        end_bar = evaluation_bars[-1]
        row.update(
            {
                "price_date": start_bar.timestamp.date().isoformat(),
                "price_at_recommendation": start_bar.close,
                "adjusted_price_at_recommendation": start_bar.adjusted_close,
                "evaluation_price_date": end_bar.timestamp.date().isoformat(),
                "price_at_evaluation": end_bar.close,
                "adjusted_price_at_evaluation": end_bar.adjusted_close,
            }
        )
        if len(bars) < technical_parameters.minimum_bars:
            row["data_status"] = (
                f"insufficient technical history: {len(bars)}/"
                f"{technical_parameters.minimum_bars} daily bars"
            )
            rows.append(row)
            continue

        snapshot = make_snapshot(item, data_agent)
        technical = technical_agent.analyze(snapshot)
        risk = risk_agent.assess_asset(profile, snapshot, technical, proposed_weight=0.02)
        findings = [technical.finding]
        row.update(
            {
                "technical_score": technical.finding.score,
                "technical_regime": technical.trend_regime.value,
                "technical_timing": technical.timing.action.value,
                "technical_timing_strength": technical.timing.strength,
                "technical_timing_confidence": technical.timing.confidence,
                "annual_volatility": technical.annual_volatility,
                "max_drawdown": technical.max_drawdown,
                "risk_veto": risk.finding.risk_veto,
                "risk_breaches": list(risk.breaches),
            }
        )

        parsed = company["fundamentals"]
        row["model_errors"].extend(parsed.get("errors", []))
        row["model_errors"].append(
            "legacy Yahoo/manual DCF disabled; rerun with SEC XBRL and market-backed WACC"
        )
        findings.append(neutral_fundamental_finding(snapshot))
        findings.append(risk.finding)
        decision = committee.decide(tuple(findings))
        decisions[symbol] = decision
        row.update(
            {
                "action": decision.action.value.upper(),
                "action_es": action_in_spanish(decision.action),
                "committee_score": decision.score,
                "committee_confidence": decision.confidence,
                "dissenting_agents": list(decision.dissenting_agents),
                "data_status": status_for(row),
            }
        )
        total_return = end_bar.adjusted_close / start_bar.adjusted_close - 1
        direction = action_direction(decision.action)
        row["underlying_total_return_pct"] = total_return
        row["profit_loss_per_share"] = direction * start_bar.close * total_return
        row["directional_return_pct"] = direction * total_return
        row["correct_direction"] = None if direction == 0 else direction * total_return > 0
        rows.append(row)

    portfolio_summary = run_portfolio_model(profile, prepared, decisions, rows)
    benchmark = benchmark_return(benchmark_raw)
    summary = summarize(rows, portfolio_summary, benchmark, universe)
    return rows, summary


def parse_price_bars(payload, symbol: str, retrieved_at: datetime):
    try:
        result = payload["chart"]["result"][0]
        timestamps = result["timestamp"]
        quote = result["indicators"]["quote"][0]
        adjusted = result["indicators"].get("adjclose", [{}])[0].get("adjclose", [])
    except (KeyError, IndexError, TypeError):
        return ()
    bars = []
    for index, timestamp in enumerate(timestamps):
        close = at(quote.get("close"), index)
        adjusted_close = at(adjusted, index) or close
        if close is None or adjusted_close is None or close <= 0 or adjusted_close <= 0:
            continue
        open_price = at(quote.get("open"), index) or close
        high = max(at(quote.get("high"), index) or close, open_price, close)
        low = min(at(quote.get("low"), index) or close, open_price, close)
        available_at = datetime.fromtimestamp(timestamp, tz=UTC)
        bars.append(
            PriceBar(
                symbol=symbol,
                timestamp=available_at,
                open=float(open_price),
                high=float(high),
                low=float(low),
                close=float(close),
                adjusted_close=float(adjusted_close),
                volume=float(at(quote.get("volume"), index) or 0),
                currency="USD",
                provenance=DataProvenance(
                    source="yahoo-chart",
                    retrieved_at=retrieved_at,
                    available_at=min(available_at, retrieved_at),
                    raw_reference=(f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"),
                    adjustments=("adjusted-close-used-for-total-return",),
                ),
            )
        )
    return tuple(sorted(bars, key=lambda bar: bar.timestamp))


def parse_fundamentals(payload, sector: str, symbol: str):
    facts = extract_facts(payload)
    errors = []
    fcf = ttm(facts, "quarterlyFreeCashFlow")
    if fcf is None:
        operating_cash = ttm(facts, "quarterlyOperatingCashFlow")
        capex = ttm(facts, "quarterlyCapitalExpenditure")
        if operating_cash is not None and capex is not None:
            fcf = operating_cash + capex
    net_income = ttm(facts, "quarterlyNetIncome")
    shares = latest(facts, "quarterlyOrdinarySharesNumber") or latest(
        facts, "quarterlyDilutedAverageShares"
    )
    if shares is not None:
        shares *= SHARE_EQUIVALENT_MULTIPLIERS.get(symbol, 1.0)
    period = latest_period(facts)
    if shares is None or shares <= 0:
        errors.append("missing positive share count")
    if sector == "Financials":
        base = net_income
        metric_name = "P/E"
        valuation_method = "earnings-discount proxy"
    else:
        base = fcf
        metric_name = "P/FCF"
        valuation_method = "free-cash-flow DCF"
    if base is None:
        errors.append("missing four-quarter base cash flow or earnings")
    metric_per_share = base / shares if base is not None and shares not in (None, 0) else None
    return {
        "valuation_method": valuation_method,
        "metric_name": metric_name,
        "metric_per_share": metric_per_share,
        "base_value": base,
        "fundamental_period": period.isoformat() if period else None,
        "errors": errors,
    }


def extract_facts(payload):
    facts = defaultdict(list)
    try:
        results = payload["timeseries"]["result"]
    except (KeyError, TypeError):
        return facts
    for result in results:
        types = result.get("meta", {}).get("type", [])
        if not types:
            continue
        fact_type = types[0]
        for observation in result.get(fact_type, []):
            try:
                as_of = date.fromisoformat(observation["asOfDate"])
                value = float(observation["reportedValue"]["raw"])
            except (KeyError, TypeError, ValueError):
                continue
            if as_of <= FUNDAMENTAL_PERIOD_CUTOFF and math.isfinite(value):
                facts[fact_type].append((as_of, value))
    for fact_type in facts:
        facts[fact_type].sort(reverse=True)
    return facts


def build_peer_observations(prepared):
    peers = defaultdict(list)
    for symbol, company in prepared.items():
        bars = tuple(bar for bar in company["bars"] if bar.timestamp.date() <= RECOMMENDATION_DATE)
        fundamentals = company["fundamentals"]
        metric = fundamentals.get("metric_per_share")
        if not bars or metric is None or metric <= 0:
            continue
        multiple = bars[-1].close / metric
        if not math.isfinite(multiple) or not 1 <= multiple <= 100:
            continue
        key = (company["item"]["sector"], fundamentals["metric_name"])
        peers[key].append(ComparableObservation(symbol=symbol, multiple=multiple, metric=key[1]))
    return peers


def build_profile(universe):
    sectors = {item["sector"] for item in universe}
    return InvestorProfileAgent().create(
        InvestorProfileRequest(
            objectives=("Cross-sectional S&P 500 research backtest",),
            horizon_years=5,
            base_currency="USD",
            risk_tolerance=RiskTolerance.MODERATE,
            min_cash_weight=0.05,
            max_position_weight=0.02,
            max_drawdown=0.45,
            max_annual_volatility=0.60,
            minimum_daily_dollar_volume=10_000_000,
            sector_max_weights={sector: 0.25 for sector in sectors},
        )
    )


class PreparedMarketData:
    name = "point-in-time-cache"

    def __init__(self, prepared):
        self._prepared = prepared

    def history(self, symbol, start, end, interval="1d"):
        del start, end, interval
        return self._prepared[symbol]["bars"]


def make_snapshot(item, data_agent):
    as_of = datetime.combine(RECOMMENDATION_DATE, datetime_time.max, tzinfo=UTC)
    snapshot = data_agent.collect(
        AssetDataRequest(
            symbol=item["index_symbol"],
            start=PRICE_START,
            end=RECOMMENDATION_DATE,
            as_of=as_of,
        )
    )
    evidence = snapshot.evidence + (
        EvidenceReference(
            source="wikipedia-sp500-revision",
            reference=UNIVERSE_URL,
            observed_at=datetime(2026, 6, 30, 3, 37, 58, tzinfo=UTC),
        ),
    )
    return replace(snapshot, evidence=evidence)


def neutral_fundamental_finding(snapshot):
    return AgentFinding(
        agent="fundamental",
        subject=snapshot.symbol,
        score=0.0,
        confidence=0.0,
        thesis="Fundamental inputs were insufficient for a point-in-time valuation.",
        evidence=snapshot.evidence,
        risks=("Fundamental model unavailable",),
        invalidation_conditions=("Required historical facts become available",),
    )


def run_portfolio_model(profile, prepared, decisions, rows):
    eligible_returns = {}
    metadata = {}
    for row in rows:
        symbol = row["symbol"]
        bars = tuple(
            bar for bar in prepared[symbol]["bars"] if bar.timestamp.date() <= RECOMMENDATION_DATE
        )
        if symbol not in decisions or len(bars) < 61:
            continue
        prices = [bar.adjusted_close for bar in bars[-61:]]
        eligible_returns[symbol] = tuple(
            current / previous - 1 for previous, current in pairwise(prices)
        )
        metadata[symbol] = AssetMetadata(
            sector=prepared[symbol]["item"]["sector"],
            country="United States",
        )
    result = {
        "status": "not run",
        "approved": False,
        "expected_annual_return": None,
        "annual_volatility": None,
        "realized_return": None,
        "weights": {},
        "error": None,
    }
    try:
        plan = PortfolioConstructionAgent().construct(
            PortfolioConstructionInputs(
                profile=profile,
                returns=eligible_returns,
                metadata=metadata,
                decisions=decisions,
                backend="inverse_volatility",
            )
        )
        risk = RiskAgent().assess_portfolio(
            profile,
            plan,
            datetime.combine(RECOMMENDATION_DATE, datetime_time.max, tzinfo=UTC),
        )
        row_by_symbol = {row["symbol"]: row for row in rows}
        realized = sum(
            weight * (row_by_symbol[symbol].get("underlying_total_return_pct") or 0.0)
            for symbol, weight in plan.allocation.weights.items()
        )
        for symbol, weight in plan.allocation.weights.items():
            row_by_symbol[symbol]["target_weight"] = weight
        result.update(
            {
                "status": "completed",
                "approved": risk.approved,
                "expected_annual_return": plan.allocation.expected_annual_return,
                "annual_volatility": plan.allocation.annual_volatility,
                "realized_return": realized,
                "weights": dict(plan.allocation.weights),
                "risk_breaches": list(risk.breaches),
            }
        )
    except Exception as exc:  # noqa: BLE001 - report optimizer failure in the output
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def benchmark_return(raw):
    bars = parse_price_bars(raw.get("prices"), "SPY", datetime.now(UTC))
    start = [bar for bar in bars if bar.timestamp.date() <= RECOMMENDATION_DATE]
    end = [bar for bar in bars if bar.timestamp.date() <= EVALUATION_DATE]
    if not start or not end:
        return None
    return end[-1].adjusted_close / start[-1].adjusted_close - 1


def summarize(rows, portfolio, benchmark, universe):
    priced = [row for row in rows if row.get("price_at_recommendation") is not None]
    valued = [row for row in rows if row.get("blended_fair_value") is not None]
    directional = [row for row in rows if row.get("correct_direction") is not None]
    action_counts = Counter(row.get("action") or "UNAVAILABLE" for row in rows)
    prior_evaluation_closes = sum(
        row.get("evaluation_price_date") != EVALUATION_DATE.isoformat() for row in priced
    )
    return {
        "universe_revision": UNIVERSE_REVISION,
        "universe_source": UNIVERSE_URL,
        "universe_securities": len(universe),
        "recommendation_date": RECOMMENDATION_DATE.isoformat(),
        "evaluation_date": EVALUATION_DATE.isoformat(),
        "fundamental_period_cutoff": FUNDAMENTAL_PERIOD_CUTOFF.isoformat(),
        "price_coverage": len(priced),
        "valuation_coverage": len(valued),
        "directional_recommendations": len(directional),
        "action_counts": dict(sorted(action_counts.items())),
        "directional_win_rate": (
            sum(bool(row["correct_direction"]) for row in directional) / len(directional)
            if directional
            else None
        ),
        "mean_directional_return": (
            statistics.mean(row["directional_return_pct"] for row in directional)
            if directional
            else None
        ),
        "median_directional_return": (
            statistics.median(row["directional_return_pct"] for row in directional)
            if directional
            else None
        ),
        "mean_profit_loss_per_share": (
            statistics.mean(row["profit_loss_per_share"] for row in directional)
            if directional
            else None
        ),
        "sp500_spy_total_return": benchmark,
        "portfolio": portfolio,
        "methodology_notes": [
            "Universe is Wikipedia revision immediately before 2026-07-01.",
            "Signals use prices through 2026-07-01 only.",
            "Evaluation uses adjusted total return through 2026-07-27.",
            "Fundamental statement periods after 2026-03-31 are excluded.",
            "Yahoo does not expose filing-known-at timestamps; later restatements may leak.",
            "Financials use an earnings-discount proxy because FCFF DCF is unsuitable.",
            "BRK.B share counts are converted from Class A equivalents at 1:1,500.",
            "BUY is measured as one long share; SELL/REDUCE as one hypothetical short share; HOLD has zero directional P/L.",
            "Dollar P/L applies adjusted total return to the raw July 1 close, including distributions.",
            f"{prior_evaluation_closes} securities use the last valid close before July 27 because that session was null in the source feed.",
            "No commissions, taxes, borrow costs, spread or slippage are included.",
        ],
    }


def write_outputs(output_dir: Path, rows, summary):
    ordered = sorted(
        rows,
        key=lambda row: (
            {"BUY": 0, "HOLD": 1, "REDUCE": 2, "SELL": 3}.get(row.get("action"), 4),
            -(row.get("committee_score") or -99),
        ),
    )
    payload = {"summary": summary, "results": ordered}
    atomic_write(
        output_dir / "sp500_backtest_2026-07-01.json",
        json.dumps(payload, indent=2, sort_keys=True, default=json_default),
    )
    atomic_write(output_dir / "sp500_backtest_2026-07-01.md", markdown_report(ordered, summary))
    atomic_write(output_dir / "sp500_backtest_2026-07-01.html", html_report(ordered, summary))


def markdown_report(rows, summary):
    ranked_buys = [row for row in rows if row.get("action") == "BUY"][:25]
    ranked_sells = sorted(
        (row for row in rows if row.get("action") in {"SELL", "REDUCE"}),
        key=lambda row: row.get("committee_score") or 99,
    )[:25]
    lines = [
        "# Backtest point-in-time del S&P 500",
        "",
        f"Fecha de recomendacion: {RECOMMENDATION_DATE.isoformat()}.",
        f"Fecha de evaluacion: {EVALUATION_DATE.isoformat()}.",
        f"Acciones en el universo: {summary['universe_securities']}.",
        f"Cobertura de valuacion: {summary['valuation_coverage']}.",
        f"Conteo de acciones: {summary['action_counts']}.",
        f"Acierto direccional: {percent(summary['directional_win_rate'])}.",
        f"Retorno direccional medio: {percent(summary['mean_directional_return'])}.",
        f"Retorno total de SPY: {percent(summary['sp500_spy_total_return'])}.",
        f"Retorno del portfolio modelo: {percent(summary['portfolio'].get('realized_return'))}.",
        "",
        "## Compras mejor rankeadas",
        "",
        markdown_table(ranked_buys),
        "",
        "## Ventas y reducciones de mayor conviccion",
        "",
        markdown_table(ranked_sells),
        "",
        "## Limitaciones",
        "",
    ]
    lines.extend(f"- {note}" for note in summary["methodology_notes"])
    return "\n".join(lines) + "\n"


def markdown_table(rows):
    lines = [
        "| Simbolo | Accion | Valor razonable | Precio 1 Jul | Precio 27 Jul | P/L por accion |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            "| {symbol} | {action} | {fair} | {start} | {end} | {pnl} |".format(
                symbol=row["symbol"],
                action=row.get("action_es") or "N/D",
                fair=money(row.get("blended_fair_value")),
                start=money(row.get("price_at_recommendation")),
                end=money(row.get("price_at_evaluation")),
                pnl=money(row.get("profit_loss_per_share")),
            )
        )
    return "\n".join(lines)


def html_report(rows, summary):
    result_rows = []
    for row in rows:
        result_rows.append(
            "<tr data-action='{data_action}'>"
            "<td>{symbol}</td><td>{company}</td><td>{sector}</td><td>{method}</td>"
            "<td>{dcf}</td><td>{comps}</td><td>{fair}</td><td>{display_action}</td>"
            "<td>{start}</td><td>{end}</td><td>{pnl}</td><td>{ret}</td>"
            "<td>{score}</td><td>{weight}</td><td>{status}</td></tr>".format(
                symbol=html.escape(row["symbol"]),
                company=html.escape(row["company"]),
                sector=html.escape(row["sector"]),
                method=html.escape(row.get("valuation_method") or "N/A"),
                dcf=money(row.get("dcf_value_per_share")),
                comps=money(row.get("comparables_value_per_share")),
                fair=money(row.get("blended_fair_value")),
                data_action=html.escape(row.get("action") or "N/A"),
                display_action=html.escape(row.get("action_es") or "N/D"),
                start=money(row.get("price_at_recommendation")),
                end=money(row.get("price_at_evaluation")),
                pnl=money(row.get("profit_loss_per_share")),
                ret=percent(row.get("directional_return_pct")),
                score=number(row.get("committee_score")),
                weight=percent(row.get("target_weight")),
                status=html.escape(row.get("data_status") or ""),
            )
        )
    notes = "".join(f"<li>{html.escape(note)}</li>" for note in summary["methodology_notes"])
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><title>Backtest del S&amp;P 500</title>
<style>
body{{font-family:Arial,sans-serif;margin:24px;color:#17202a;background:#f6f8fa}}
h1{{font-size:24px}} .cards{{display:flex;gap:12px;flex-wrap:wrap;margin:18px 0}}
.card{{background:white;border:1px solid #d8dee4;padding:12px;min-width:170px}}
.card strong{{display:block;font-size:20px;margin-top:5px}}
input,select{{padding:8px;margin:8px 8px 12px 0}}
.table-wrap{{overflow:auto;max-height:70vh;background:white;border:1px solid #d8dee4}}
table{{border-collapse:collapse;width:100%;font-size:12px;white-space:nowrap}}
th{{position:sticky;top:0;background:#1f4e78;color:white;text-align:left;padding:8px}}
td{{border-bottom:1px solid #e5e7eb;padding:7px;text-align:right}}
td:nth-child(-n+4),td:last-child{{text-align:left}} tr:hover{{background:#eef6ff}}
.note{{max-width:1000px;background:#fff8dc;border-left:4px solid #c99500;padding:10px 16px}}
</style></head><body>
<h1>Backtest point-in-time del S&amp;P 500</h1>
<p>Recomendacion: cierre del 2026-07-01. Evaluacion: cierre del 2026-07-27.</p>
<div class="cards">
<div class="card">Acciones<strong>{summary["universe_securities"]}</strong></div>
<div class="card">Valuaciones<strong>{summary["valuation_coverage"]}</strong></div>
<div class="card">Acierto direccional<strong>{percent(summary["directional_win_rate"])}</strong></div>
<div class="card">Retorno direccional medio<strong>{percent(summary["mean_directional_return"])}</strong></div>
<div class="card">Portfolio modelo<strong>{percent(summary["portfolio"].get("realized_return"))}</strong></div>
<div class="card">SPY<strong>{percent(summary["sp500_spy_total_return"])}</strong></div>
</div>
<input id="search" placeholder="Buscar simbolo o empresa"><select id="action">
<option value="">Todas las acciones</option><option>BUY</option><option>HOLD</option>
<option>REDUCE</option><option>SELL</option><option>N/A</option></select>
<div class="table-wrap"><table><thead><tr><th>Simbolo</th><th>Empresa</th><th>Sector</th>
<th>Metodo</th><th>DCF</th><th>Comparables</th><th>Valor razonable</th><th>Accion</th>
<th>Precio 1 Jul</th><th>Precio 27 Jul</th><th>P/L por accion</th><th>Retorno direccional</th>
<th>Score del comite</th><th>Peso objetivo</th><th>Estado</th></tr></thead>
<tbody>{"".join(result_rows)}</tbody></table></div>
<div class="note"><h2>Limitaciones del metodo</h2><ul>{notes}</ul></div>
<script>
const search=document.getElementById('search'), action=document.getElementById('action');
function filterRows(){{const q=search.value.toLowerCase(),a=action.value;
document.querySelectorAll('tbody tr').forEach(r=>{{r.style.display=(!q||r.innerText.toLowerCase().includes(q))&&(!a||r.dataset.action===a)?'':'none';}})}}
search.addEventListener('input',filterRows);action.addEventListener('change',filterRows);
</script></body></html>"""


def base_row(item, errors):
    return {
        "symbol": item["index_symbol"],
        "yahoo_symbol": item["yahoo_symbol"],
        "company": item["company"],
        "sector": item["sector"],
        "sub_industry": item["sub_industry"],
        "cik": item["cik"],
        "valuation_method": None,
        "fundamental_period": None,
        "base_cash_flow_or_earnings": None,
        "metric_per_share": None,
        "discount_rate": None,
        "terminal_growth_rate": None,
        "dcf_value_per_share": None,
        "comparables_value_per_share": None,
        "selected_peer_multiple": None,
        "peer_count": None,
        "blended_fair_value": None,
        "margin_of_safety": None,
        "price_date": None,
        "price_at_recommendation": None,
        "adjusted_price_at_recommendation": None,
        "evaluation_price_date": None,
        "price_at_evaluation": None,
        "adjusted_price_at_evaluation": None,
        "fundamental_score": None,
        "quality_score": None,
        "technical_score": None,
        "relative_score": None,
        "annual_volatility": None,
        "max_drawdown": None,
        "risk_veto": None,
        "risk_breaches": [],
        "committee_score": None,
        "committee_confidence": None,
        "dissenting_agents": [],
        "action": None,
        "action_es": None,
        "target_weight": 0.0,
        "underlying_total_return_pct": None,
        "directional_return_pct": None,
        "profit_loss_per_share": None,
        "correct_direction": None,
        "data_status": "not analyzed",
        "fetch_errors": list(errors),
        "model_errors": [],
        "price_source": (
            f"https://query1.finance.yahoo.com/v8/finance/chart/{item['yahoo_symbol']}"
        ),
        "fundamental_source": (
            "https://query2.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/"
            f"timeseries/{item['yahoo_symbol']}"
        ),
        "universe_source": UNIVERSE_URL,
    }


def status_for(row):
    if row["model_errors"]:
        return "partial model coverage"
    if row["blended_fair_value"] is None:
        return "technical/risk only; valuation unavailable"
    return "complete"


def action_direction(action):
    if action == SignalAction.BUY:
        return 1
    if action in {SignalAction.SELL, SignalAction.REDUCE}:
        return -1
    return 0


def action_in_spanish(action):
    return {
        SignalAction.BUY: "COMPRAR",
        SignalAction.HOLD: "MANTENER",
        SignalAction.REDUCE: "REDUCIR/VENDER",
        SignalAction.SELL: "VENDER",
    }[action]


def ttm(facts, fact_type):
    observations = facts.get(fact_type, [])
    if len(observations) < 4:
        return None
    return sum(value for _, value in observations[:4])


def latest(facts, fact_type):
    observations = facts.get(fact_type, [])
    return observations[0][1] if observations else None


def latest_period(facts):
    dates = [values[0][0] for values in facts.values() if values]
    return max(dates) if dates else None


def year_over_year(facts, fact_type):
    observations = facts.get(fact_type, [])
    if len(observations) < 5 or observations[4][1] == 0:
        return None
    return observations[0][1] / observations[4][1] - 1


def at(values, index):
    if not values or index >= len(values):
        return None
    value = values[index]
    return value if value is not None and math.isfinite(float(value)) else None


def epoch(value: date):
    return int(datetime.combine(value, datetime_time.min, tzinfo=UTC).timestamp())


def clamp(value, minimum, maximum):
    return max(minimum, min(float(value), maximum))


def atomic_write(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def json_default(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "value"):
        return value.value
    return asdict(value)


def money(value):
    return "N/A" if value is None or not math.isfinite(value) else f"${value:,.2f}"


def percent(value):
    return "N/A" if value is None or not math.isfinite(value) else f"{value:.2%}"


def number(value):
    return "N/A" if value is None or not math.isfinite(value) else f"{value:.3f}"


if __name__ == "__main__":
    main()

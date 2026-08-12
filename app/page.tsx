"use client";

import {
  Activity,
  BarChart3,
  Clock3,
  Layers3,
  LineChart,
  RefreshCw,
  WalletCards
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart as ReLineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";
import {
  buildCompositeBenchmark,
  buildPortfolioView,
  buildSimilarPerformance,
  correlation,
  dailyReturns
} from "./lib/portfolio";
import type { MarketResponse, PortfolioConfig } from "./lib/types";

const ranges = [
  { value: "1mo", label: "1M" },
  { value: "3mo", label: "3M" },
  { value: "6mo", label: "6M" },
  { value: "1y", label: "1Y" },
  { value: "2y", label: "2Y" },
  { value: "5y", label: "5Y" }
];

export default function Home() {
  const [range, setRange] = useState("1y");
  const [activeTab, setActiveTab] = useState<"performance" | "decomposition">("performance");
  const [portfolioConfig, setPortfolioConfig] = useState<PortfolioConfig | null>(null);
  const [market, setMarket] = useState<MarketResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const symbols = useMemo(() => {
    if (!portfolioConfig) return [];
    const all = [
      portfolioConfig.benchmark,
      ...portfolioConfig.holdings.map((holding) => holding.symbol),
      ...portfolioConfig.holdings.map((holding) => holding.benchmark).filter(Boolean),
      ...portfolioConfig.similarPortfolios.flatMap((portfolio) =>
        portfolio.holdings.map((holding) => holding.symbol)
      )
    ];
    return Array.from(new Set(all));
  }, [portfolioConfig]);

  async function loadPortfolio() {
    const response = await fetch("/api/portfolio");
    if (!response.ok) throw new Error("No se pudo cargar el portafolio.");
    return (await response.json()) as PortfolioConfig;
  }

  async function loadMarket() {
    if (!symbols.length) return;
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`/api/market?symbols=${symbols.join(",")}&range=${range}`);
      if (!response.ok) throw new Error("No se pudieron cargar las cotizaciones.");
      setMarket((await response.json()) as MarketResponse);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Error inesperado.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const nextPortfolio = await loadPortfolio();
        if (!cancelled) setPortfolioConfig(nextPortfolio);
      } catch (caught) {
        if (!cancelled) {
          setError(caught instanceof Error ? caught.message : "Error inesperado.");
          setLoading(false);
        }
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!symbols.length) return;
    loadMarket();
    const timer = window.setInterval(async () => {
      try {
        const nextPortfolio = await loadPortfolio();
        setPortfolioConfig(nextPortfolio);
      } finally {
        await loadMarket();
      }
    }, 60_000);
    return () => window.clearInterval(timer);
  }, [range, symbols]);

  const benchmark = market?.series.find((item) => item.symbol === portfolioConfig?.benchmark);
  const view = market && portfolioConfig
    ? buildPortfolioView(portfolioConfig.holdings, market.series, benchmark)
    : null;
  const compositeBenchmark =
    market && portfolioConfig ? buildCompositeBenchmark(portfolioConfig.holdings, market.series) : [];
  const performanceData =
    view?.performance.map((point) => {
      const composite = compositeBenchmark.find((item) => item.date === point.date);
      return { ...point, benchmark: composite?.portfolio };
    }) ?? [];
  const portfolioReturns = view ? dailyReturns(view.performance) : [];

  const comparisons =
    market && view && portfolioConfig
      ? portfolioConfig.similarPortfolios.map((similar) => {
          const performance = buildSimilarPerformance(similar, market.series);
          const returns = dailyReturns(performance);
          return {
            name: similar.name,
            symbols: similar.holdings.map((holding) => holding.symbol).join(", "),
            returnPercent: performance.at(-1)?.portfolio ?? 0,
            correlation: correlation(portfolioReturns, returns)
          };
        })
      : [];

  return (
    <main className="shell">
      <header className="topbar">
        <div className="brand">
          <div className="mark">
            <WalletCards size={20} />
          </div>
          <div>
            <h1>Investement Portfolio</h1>
            <p>Dashboard en tiempo real con benchmark ponderado por exposición</p>
          </div>
        </div>
        <div className="toolbar">
          <select aria-label="Rango" value={range} onChange={(event) => setRange(event.target.value)}>
            {ranges.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
          <button className="ghost-button" type="button" onClick={loadMarket} disabled={loading}>
            <RefreshCw size={16} />
            Actualizar
          </button>
        </div>
      </header>

      <section className="content">
        {error ? <div className="error">{error}</div> : null}
        <nav className="tabs" aria-label="Vistas del portfolio">
          <button
            className={activeTab === "performance" ? "active" : ""}
            type="button"
            onClick={() => setActiveTab("performance")}
          >
            <LineChart size={16} />
            Rendimiento
          </button>
          <button
            className={activeTab === "decomposition" ? "active" : ""}
            type="button"
            onClick={() => setActiveTab("decomposition")}
          >
            <Layers3 size={16} />
            Descomposición
          </button>
        </nav>

        <section className="kpis">
          <Metric
            label="Valor total"
            value={money(view?.totalValue ?? 0)}
            detail={portfolioConfig?.baseCurrency ?? "USD"}
          />
          <Metric
            label="Resultado"
            value={money(view?.totalPnl ?? 0)}
            detail={percent(view?.totalPnlPercent ?? 0)}
            trend={view?.totalPnl ?? 0}
          />
          <Metric
            label="Cambio diario"
            value={money(view?.dayChange ?? 0)}
            detail={market?.asOf ? `Actualizado ${time(market.asOf)}` : "Cargando"}
            trend={view?.dayChange ?? 0}
          />
          <Metric
            label="Vs benchmark ponderado"
            value={percent((performanceData.at(-1)?.portfolio ?? 0) - (performanceData.at(-1)?.benchmark ?? 0))}
            detail="Diferencial del rango"
            trend={(performanceData.at(-1)?.portfolio ?? 0) - (performanceData.at(-1)?.benchmark ?? 0)}
          />
        </section>

        {activeTab === "performance" ? (
          <>
            <section className="grid">
              <div className="panel">
                <div className="panel-header">
                  <h2>Evolución</h2>
                  <span className="status">
                    <LineChart size={14} /> Portfolio vs benchmark ponderado
                  </span>
                </div>
                <div className="chart">
                  <ResponsiveContainer>
                    <ReLineChart data={performanceData}>
                      <CartesianGrid stroke="#e5ebe4" vertical={false} />
                      <XAxis dataKey="date" tickLine={false} minTickGap={32} />
                      <YAxis tickFormatter={(value) => `${value}%`} width={48} />
                      <Tooltip formatter={(value: number) => percent(value)} />
                      <Line type="monotone" dataKey="portfolio" stroke="#0f8b5f" strokeWidth={2.4} dot={false} />
                      <Line type="monotone" dataKey="benchmark" stroke="#2364aa" strokeWidth={2} dot={false} />
                    </ReLineChart>
                  </ResponsiveContainer>
                </div>
              </div>

              <div className="panel">
                <div className="panel-header">
                  <h2>Composición</h2>
                  <BarChart3 size={18} color="#2364aa" />
                </div>
                <div className="bars">
                  {view?.allocation.map((item) => (
                    <div className="bar-row" key={item.symbol}>
                      <strong>{item.symbol}</strong>
                      <div className="bar">
                        <span style={{ width: `${Math.min(item.weight, 100)}%` }} />
                      </div>
                      <span>{percent(item.weight, 1)}</span>
                    </div>
                  ))}
                </div>
              </div>
            </section>

            <section className="grid">
              <div className="panel">
                <div className="panel-header">
                  <h2>Comparables</h2>
                  <span className="status">Portafolios similares</span>
                </div>
                <div className="compare-list">
                  {comparisons.map((item) => (
                    <div className="compare-row" key={item.name}>
                      <div>
                        <strong>{item.name}</strong>
                        <span>{item.symbols}</span>
                      </div>
                      <strong className={classFor(item.returnPercent)}>{percent(item.returnPercent)}</strong>
                      <span>{percent(item.correlation * 100, 0)} corr.</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="panel">
                <div className="panel-header">
                  <h2>Rendimiento diario</h2>
                  <Clock3 size={18} color="#b47b24" />
                </div>
                <div className="chart">
                  <ResponsiveContainer>
                    <AreaChart data={performanceData}>
                      <CartesianGrid stroke="#e5ebe4" vertical={false} />
                      <XAxis dataKey="date" hide />
                      <YAxis hide />
                      <Tooltip formatter={(value: number) => percent(value)} />
                      <Area type="monotone" dataKey="portfolio" stroke="#b47b24" fill="#f1dfbe" />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </section>
          </>
        ) : (
          <>
            <section className="panel">
              <div className="panel-header">
                <h2>Descomposición por categoría</h2>
                <span className="status">
                  <Layers3 size={14} /> Acciones, ETFs y fondos
                </span>
              </div>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Categoría</th>
                      <th># activos</th>
                      <th>Valor compra</th>
                      <th>Valor actual</th>
                      <th>P&L diario</th>
                      <th>P&L diario %</th>
                      <th>P&L acum.</th>
                      <th>P&L acum. %</th>
                    </tr>
                  </thead>
                  <tbody>
                    {view?.decomposition.map((row) => (
                      <tr key={row.category}>
                        <td>{row.category}</td>
                        <td>{row.count}</td>
                        <td>{row.cost === null ? "n/a" : money(row.cost)}</td>
                        <td>{money(row.value)}</td>
                        <td className={classFor(row.dayChange)}>{money(row.dayChange)}</td>
                        <td className={classFor(row.dayChangePercent)}>{percent(row.dayChangePercent)}</td>
                        <td className={classFor(row.pnl ?? 0)}>{row.pnl === null ? "n/a" : money(row.pnl)}</td>
                        <td className={classFor(row.pnlPercent ?? 0)}>
                          {row.pnlPercent === null ? "n/a" : percent(row.pnlPercent)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

            <section className="panel">
              <div className="panel-header">
                <h2>Detalle de activos</h2>
                <span className="status">
                  <Activity size={14} /> Precios de mercado
                </span>
              </div>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Símbolo</th>
                      <th>Categoría</th>
                      <th>Cantidad</th>
                      <th>Precio</th>
                      <th>Valor compra</th>
                      <th>Valor actual</th>
                      <th>Peso</th>
                      <th>P&L diario</th>
                      <th>P&L diario %</th>
                      <th>P&L acum.</th>
                      <th>P&L acum. %</th>
                    </tr>
                  </thead>
                  <tbody>
                    {view?.positions.map((position) => (
                      <tr key={position.symbol}>
                        <td>{position.symbol}</td>
                        <td>{position.category}</td>
                        <td>{number(position.quantity)}</td>
                        <td>{money(position.price)}</td>
                        <td>{position.cost === null ? "n/a" : money(position.cost)}</td>
                        <td>{money(position.value)}</td>
                        <td>{percent(position.weight, 1)}</td>
                        <td className={classFor(position.dayChange)}>{money(position.dayChange)}</td>
                        <td className={classFor(position.dayChangePercent)}>{percent(position.dayChangePercent)}</td>
                        <td className={classFor(position.pnl ?? 0)}>
                          {position.pnl === null ? "n/a" : money(position.pnl)}
                        </td>
                        <td className={classFor(position.pnlPercent ?? 0)}>
                          {position.pnlPercent === null ? "n/a" : percent(position.pnlPercent)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          </>
        )}
      </section>
    </main>
  );
}

function Metric({
  label,
  value,
  detail,
  trend
}: {
  label: string;
  value: string;
  detail: string;
  trend?: number;
}) {
  return (
    <div className="metric">
      <p className="label">{label}</p>
      <p className={`value ${trend === undefined ? "" : classFor(trend)}`}>{value}</p>
      <p className="delta">{detail}</p>
    </div>
  );
}

function money(value: number) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(value);
}

function percent(value: number, digits = 2) {
  return `${value.toFixed(digits)}%`;
}

function number(value: number) {
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 4 }).format(value);
}

function time(value: string) {
  return new Intl.DateTimeFormat("es-UY", {
    hour: "2-digit",
    minute: "2-digit"
  }).format(new Date(value));
}

function classFor(value: number) {
  if (value > 0) return "positive";
  if (value < 0) return "negative";
  return "";
}

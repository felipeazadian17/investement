"use client";

import {
  Activity,
  ArrowDownRight,
  ArrowUpRight,
  BriefcaseBusiness,
  CalendarDays,
  ChartPie,
  ChevronDown,
  CircleDollarSign,
  Clock3,
  ExternalLink,
  Globe2,
  Info,
  Layers3,
  LineChart,
  Newspaper,
  Siren,
  RefreshCw,
  Search,
  ShieldCheck,
  WalletCards
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart as ReLineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";
import {
  buildBenchmarkMix,
  buildCompositeBenchmark,
  buildPortfolioView,
  buildSimilarPerformance,
  correlation,
  dailyReturns,
  type CategoryView,
  type PositionView
} from "./lib/portfolio";
import type { MarketResponse, NewsKind, NewsResponse, PortfolioConfig } from "./lib/types";

const ranges = [
  { value: "1mo", label: "1M" },
  { value: "3mo", label: "3M" },
  { value: "6mo", label: "6M" },
  { value: "1y", label: "1A" },
  { value: "2y", label: "2A" },
  { value: "5y", label: "5A" }
];

const allocationColors = ["#136f63", "#2f6fbb", "#d29b2d", "#7d5ba6", "#cf6356", "#698474"];

type Tab = "overview" | "performance" | "positions" | "news";
type Sort = "value" | "day" | "return" | "symbol";

export default function Home() {
  const [range, setRange] = useState("1y");
  const [activeTab, setActiveTab] = useState<Tab>("overview");
  const [portfolioConfig, setPortfolioConfig] = useState<PortfolioConfig | null>(null);
  const [market, setMarket] = useState<MarketResponse | null>(null);
  const [news, setNews] = useState<NewsResponse | null>(null);
  const [newsLoading, setNewsLoading] = useState(false);
  const [newsError, setNewsError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("all");
  const [sort, setSort] = useState<Sort>("value");

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
    const response = await fetch("/api/portfolio", { cache: "no-store" });
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

  async function refreshAll() {
    setLoading(true);
    setError(null);
    try {
      const nextPortfolio = await loadPortfolio();
      setPortfolioConfig(nextPortfolio);
      const nextSymbols = Array.from(
        new Set([
          nextPortfolio.benchmark,
          ...nextPortfolio.holdings.map((holding) => holding.symbol),
          ...nextPortfolio.holdings.map((holding) => holding.benchmark).filter(Boolean),
          ...nextPortfolio.similarPortfolios.flatMap((portfolio) =>
            portfolio.holdings.map((holding) => holding.symbol)
          )
        ])
      );
      const response = await fetch(`/api/market?symbols=${nextSymbols.join(",")}&range=${range}`);
      if (!response.ok) throw new Error("No se pudieron actualizar las cotizaciones.");
      setMarket((await response.json()) as MarketResponse);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Error inesperado.");
    } finally {
      setLoading(false);
    }
  }

  async function loadNews() {
    setNewsLoading(true);
    setNewsError(null);
    try {
      const response = await fetch("/api/news");
      if (!response.ok) throw new Error("No se pudieron cargar las noticias.");
      setNews((await response.json()) as NewsResponse);
    } catch (caught) {
      setNewsError(caught instanceof Error ? caught.message : "Error inesperado.");
    } finally {
      setNewsLoading(false);
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
    const timer = window.setInterval(refreshAll, 60_000);
    return () => window.clearInterval(timer);
    // The symbol list is the stable trigger for a fresh market snapshot.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [range, symbols.join(",")]);

  useEffect(() => {
    if (activeTab === "news" && portfolioConfig && !news && !newsLoading) loadNews();
    // News is fetched lazily when its view is opened.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, portfolioConfig, news]);

  const benchmark = market?.series.find((item) => item.symbol === portfolioConfig?.benchmark);
  const view =
    market && portfolioConfig
      ? buildPortfolioView(
          portfolioConfig.holdings,
          market.series,
          benchmark,
          portfolioConfig.cash ?? 0
        )
      : null;
  const compositeBenchmark =
    market && portfolioConfig ? buildCompositeBenchmark(portfolioConfig.holdings, market.series) : [];
  const performanceData =
    view?.performance.map((point) => {
      const composite = compositeBenchmark.find((item) => item.date === point.date);
      return { ...point, benchmark: composite?.portfolio };
    }) ?? [];

  const portfolioReturn = performanceData.at(-1)?.portfolio ?? 0;
  const benchmarkReturn = performanceData.at(-1)?.benchmark ?? 0;
  const alpha = portfolioReturn - benchmarkReturn;
  const portfolioReturns = view ? dailyReturns(view.performance) : [];
  const benchmarkMix =
    market && portfolioConfig ? buildBenchmarkMix(portfolioConfig.holdings, market.series) : [];
  const risk = riskMetrics(performanceData);

  const comparisons =
    market && view && portfolioConfig
      ? portfolioConfig.similarPortfolios.map((similar) => {
          const performance = buildSimilarPerformance(similar, market.series);
          const returns = dailyReturns(performance);
          return {
            name: similar.name,
            symbols: similar.holdings.map((holding) => holding.symbol).join(" · "),
            returnPercent: performance.at(-1)?.portfolio ?? 0,
            correlation: correlation(portfolioReturns, returns)
          };
        })
      : [];

  const topMovers = [...(view?.positions ?? [])]
    .sort((left, right) => Math.abs(right.dayChange) - Math.abs(left.dayChange))
    .slice(0, 5);
  const topFiveWeight = [...(view?.positions ?? [])]
    .sort((left, right) => right.weight - left.weight)
    .slice(0, 5)
    .reduce((sum, position) => sum + position.weight, 0);
  const largestPosition = [...(view?.positions ?? [])].sort((left, right) => right.weight - left.weight)[0];
  const allocationData = [
    ...(view?.decomposition.map((item) => ({ name: item.category, value: item.value })) ?? []),
    ...(view && view.cash > 0 ? [{ name: "Efectivo", value: view.cash }] : [])
  ];

  const categories = view?.decomposition.map((item) => item.category) ?? [];
  const visiblePositions = useMemo(() => {
    const filtered = (view?.positions ?? []).filter((position) => {
      const matchesQuery = `${position.symbol} ${position.name}`.toLowerCase().includes(query.toLowerCase());
      const matchesCategory = category === "all" || position.category === category;
      return matchesQuery && matchesCategory;
    });
    return filtered.sort((left, right) => {
      if (sort === "symbol") return left.symbol.localeCompare(right.symbol);
      if (sort === "day") return right.dayChange - left.dayChange;
      if (sort === "return") return (right.pnlPercent ?? -Infinity) - (left.pnlPercent ?? -Infinity);
      return right.value - left.value;
    });
  }, [view, query, category, sort]);

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            <WalletCards size={19} />
          </span>
          <div>
            <strong>Portfolio</strong>
            <span>Investment dashboard</span>
          </div>
        </div>

        <div className="account-context">
          <span className={`source-dot ${portfolioConfig?.source === "snaptrade" ? "connected" : ""}`} />
          <div>
            <strong>{portfolioConfig?.account?.name ?? "Portafolio consolidado"}</strong>
            <span>{portfolioConfig?.account?.institution ?? "Fuente local"}</span>
          </div>
        </div>

        <div className="toolbar">
          <div className="freshness">
            <Clock3 size={14} />
            <span>{market?.asOf ? `Actualizado ${time(market.asOf)}` : "Sincronizando"}</span>
          </div>
          <button
            className="icon-button"
            type="button"
            onClick={refreshAll}
            disabled={loading}
            title="Actualizar datos"
            aria-label="Actualizar datos"
          >
            <RefreshCw size={17} className={loading ? "spinning" : ""} />
          </button>
        </div>
      </header>

      <main className="workspace">
        <div className="page-heading">
          <div>
            <p className="eyebrow">{portfolioConfig?.account?.institution ?? "Cuenta de inversión"}</p>
            <h1>Resumen del portafolio</h1>
          </div>
          <span className="read-only-badge">
            <ShieldCheck size={14} /> Solo lectura
          </span>
        </div>

        <nav className="tabs" aria-label="Vistas del portafolio">
          <TabButton active={activeTab === "overview"} onClick={() => setActiveTab("overview")}>
            <BriefcaseBusiness size={16} /> Resumen
          </TabButton>
          <TabButton active={activeTab === "performance"} onClick={() => setActiveTab("performance")}>
            <LineChart size={16} /> Rendimiento
          </TabButton>
          <TabButton active={activeTab === "positions"} onClick={() => setActiveTab("positions")}>
            <Layers3 size={16} /> Posiciones
          </TabButton>
          <TabButton active={activeTab === "news"} onClick={() => setActiveTab("news")}>
            <Newspaper size={16} /> Noticias
          </TabButton>
        </nav>

        {error ? <div className="error-banner">{error}</div> : null}
        {!view && loading ? <LoadingState /> : null}

        {view ? (
          <>
            <section className="balance-strip" aria-label="Resumen de saldos">
              <div className="primary-balance">
                <span>Valor total</span>
                <strong>{money(view.totalValue)}</strong>
                <Trend value={view.dayChange} percentValue={view.dayChangePercent} label="hoy" />
              </div>
              <SummaryMetric label="Invertido" value={money(view.investedValue)} detail={percent(100 - view.cashWeight, 1)} />
              <SummaryMetric label="Efectivo" value={money(view.cash)} detail={percent(view.cashWeight, 1)} />
              <SummaryMetric
                label="Ganancia total"
                value={view.totalPnl === null ? "No disponible" : signedMoney(view.totalPnl)}
                detail={view.totalPnlPercent === null ? "Sin base de costo" : signedPercent(view.totalPnlPercent)}
                trend={view.totalPnl ?? undefined}
              />
              <SummaryMetric
                label="Vs. benchmark"
                value={signedPercent(alpha)}
                detail={`En ${rangeLabel(range)}`}
                trend={alpha}
              />
            </section>

            {activeTab === "overview" ? (
              <Overview
                performanceData={performanceData}
                range={range}
                onRangeChange={setRange}
                portfolioReturn={portfolioReturn}
                benchmarkReturn={benchmarkReturn}
                topMovers={topMovers}
                allocationData={allocationData}
                totalValue={view.totalValue}
                benchmarkMix={benchmarkMix}
                largestPosition={largestPosition}
                topFiveWeight={topFiveWeight}
                cashWeight={view.cashWeight}
              />
            ) : null}

            {activeTab === "performance" ? (
              <PerformanceView
                performanceData={performanceData}
                range={range}
                onRangeChange={setRange}
                portfolioReturn={portfolioReturn}
                benchmarkReturn={benchmarkReturn}
                alpha={alpha}
                risk={risk}
                benchmarkMix={benchmarkMix}
                comparisons={comparisons}
              />
            ) : null}

            {activeTab === "positions" ? (
              <PositionsView
                positions={visiblePositions}
                decomposition={view.decomposition}
                categories={categories}
                query={query}
                category={category}
                sort={sort}
                onQueryChange={setQuery}
                onCategoryChange={setCategory}
                onSortChange={setSort}
              />
            ) : null}

            {activeTab === "news" ? (
              <NewsView news={news} loading={newsLoading} error={newsError} onRetry={loadNews} />
            ) : null}
          </>
        ) : null}

        <footer className="disclosure">
          <Info size={14} />
          <span>
            Valores actuales de mercado. El historial reconstruye la composición actual y no sustituye el
            estado oficial del broker. Rendimientos pasados no garantizan resultados futuros.
          </span>
        </footer>
      </main>
    </div>
  );
}

function Overview({
  performanceData,
  range,
  onRangeChange,
  portfolioReturn,
  benchmarkReturn,
  topMovers,
  allocationData,
  totalValue,
  benchmarkMix,
  largestPosition,
  topFiveWeight,
  cashWeight
}: {
  performanceData: Array<{ date: string; portfolio: number; benchmark?: number }>;
  range: string;
  onRangeChange: (value: string) => void;
  portfolioReturn: number;
  benchmarkReturn: number;
  topMovers: PositionView[];
  allocationData: Array<{ name: string; value: number }>;
  totalValue: number;
  benchmarkMix: Array<{ symbol: string; value: number; weight: number }>;
  largestPosition?: PositionView;
  topFiveWeight: number;
  cashWeight: number;
}) {
  return (
    <div className="view-stack">
      <div className="overview-grid">
        <section className="panel performance-panel">
          <PanelHeader
            title="Evolución"
            subtitle="Composición actual vs. benchmark ponderado"
            control={<RangeControl value={range} onChange={onRangeChange} />}
          />
          <div className="chart-summary">
            <ChartLegend label="Portafolio" value={portfolioReturn} color="#136f63" />
            <ChartLegend label="Benchmark" value={benchmarkReturn} color="#2f6fbb" />
          </div>
          <PerformanceChart data={performanceData} />
        </section>

        <section className="panel movers-panel">
          <PanelHeader title="Motores de hoy" subtitle="Impacto nominal en el portafolio" />
          <div className="mover-list">
            {topMovers.map((position) => (
              <div className="mover-row" key={position.symbol}>
                <SymbolMark symbol={position.symbol} />
                <div className="mover-name">
                  <strong>{position.symbol}</strong>
                  <span>{position.name}</span>
                </div>
                <div className="mover-value">
                  <strong className={classFor(position.dayChange)}>{signedMoney(position.dayChange)}</strong>
                  <span className={classFor(position.dayChangePercent)}>
                    {signedPercent(position.dayChangePercent)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>

      <div className="analysis-grid">
        <section className="panel allocation-panel">
          <PanelHeader title="Asignación" subtitle="Distribución por estrategia y vehículo" />
          <div className="allocation-layout">
            <div className="donut-wrap">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={allocationData}
                    dataKey="value"
                    nameKey="name"
                    innerRadius="66%"
                    outerRadius="88%"
                    paddingAngle={2}
                    stroke="none"
                    isAnimationActive={false}
                  >
                    {allocationData.map((item, index) => (
                      <Cell key={item.name} fill={allocationColors[index % allocationColors.length]} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(value: number) => money(value)} />
                </PieChart>
              </ResponsiveContainer>
              <div className="donut-center">
                <span>Total</span>
                <strong>{compactMoney(totalValue)}</strong>
              </div>
            </div>
            <div className="allocation-legend">
              {allocationData.map((item, index) => (
                <div className="allocation-row" key={item.name}>
                  <span className="legend-dot" style={{ background: allocationColors[index % allocationColors.length] }} />
                  <span>{item.name}</span>
                  <strong>{percent(totalValue ? (item.value / totalValue) * 100 : 0, 1)}</strong>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="panel health-panel">
          <PanelHeader title="Diversificación" subtitle="Concentración y exposición de mercado" />
          <div className="health-metrics">
            <HealthMetric
              label="Mayor posición"
              value={largestPosition ? `${largestPosition.symbol} · ${percent(largestPosition.weight, 1)}` : "-"}
              fill={largestPosition?.weight ?? 0}
              threshold={15}
            />
            <HealthMetric label="Top 5 posiciones" value={percent(topFiveWeight, 1)} fill={topFiveWeight} threshold={50} />
            <HealthMetric label="Reserva en efectivo" value={percent(cashWeight, 1)} fill={cashWeight} threshold={10} />
          </div>
          <div className="benchmark-list">
            <span className="section-label">Benchmark compuesto</span>
            {benchmarkMix.map((item) => (
              <div className="benchmark-row" key={item.symbol}>
                <strong>{item.symbol}</strong>
                <div className="mini-track">
                  <span style={{ width: `${item.weight}%` }} />
                </div>
                <span>{percent(item.weight, 1)}</span>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}

function PerformanceView({
  performanceData,
  range,
  onRangeChange,
  portfolioReturn,
  benchmarkReturn,
  alpha,
  risk,
  benchmarkMix,
  comparisons
}: {
  performanceData: Array<{ date: string; portfolio: number; benchmark?: number }>;
  range: string;
  onRangeChange: (value: string) => void;
  portfolioReturn: number;
  benchmarkReturn: number;
  alpha: number;
  risk: { volatility: number; maxDrawdown: number; positiveDays: number };
  benchmarkMix: Array<{ symbol: string; value: number; weight: number }>;
  comparisons: Array<{ name: string; symbols: string; returnPercent: number; correlation: number }>;
}) {
  const riskData = performanceData.slice(-60).map((point, index, items) => ({
    date: point.date,
    return: index ? ((100 + point.portfolio) / (100 + items[index - 1].portfolio) - 1) * 100 : 0
  }));

  return (
    <div className="view-stack">
      <section className="performance-stats" aria-label="Estadísticas de rendimiento">
        <Stat label="Retorno estimado" value={signedPercent(portfolioReturn)} trend={portfolioReturn} />
        <Stat label="Benchmark" value={signedPercent(benchmarkReturn)} trend={benchmarkReturn} />
        <Stat label="Diferencial" value={signedPercent(alpha)} trend={alpha} />
        <Stat label="Volatilidad anualizada" value={percent(risk.volatility)} />
        <Stat label="Máx. caída" value={signedPercent(risk.maxDrawdown)} trend={risk.maxDrawdown} />
        <Stat label="Días positivos" value={percent(risk.positiveDays, 0)} />
      </section>

      <section className="panel performance-panel full-width">
        <PanelHeader
          title="Rendimiento relativo"
          subtitle="Retorno de la composición actual"
          control={<RangeControl value={range} onChange={onRangeChange} />}
        />
        <div className="chart-summary">
          <ChartLegend label="Portafolio" value={portfolioReturn} color="#136f63" />
          <ChartLegend label="Benchmark ponderado" value={benchmarkReturn} color="#2f6fbb" />
        </div>
        <PerformanceChart data={performanceData} large />
      </section>

      <div className="analysis-grid three-columns">
        <section className="panel compact-panel">
          <PanelHeader title="Volatilidad reciente" subtitle="Retornos diarios, últimas 60 ruedas" />
          <div className="small-chart">
            <ResponsiveContainer>
              <BarChart data={riskData}>
                <XAxis dataKey="date" hide />
                <YAxis hide />
                <Tooltip formatter={(value: number) => signedPercent(value)} />
                <Bar dataKey="return" radius={[2, 2, 0, 0]} isAnimationActive={false}>
                  {riskData.map((item) => (
                    <Cell key={item.date} fill={item.return >= 0 ? "#4b9b7b" : "#cf6356"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </section>

        <section className="panel compact-panel">
          <PanelHeader title="Índices de referencia" subtitle="Ponderación por exposición" />
          <div className="benchmark-detail-list">
            {benchmarkMix.map((item) => (
              <div key={item.symbol}>
                <SymbolMark symbol={item.symbol} small />
                <span>{benchmarkName(item.symbol)}</span>
                <strong>{percent(item.weight, 1)}</strong>
              </div>
            ))}
          </div>
        </section>

        <section className="panel compact-panel">
          <PanelHeader title="Portafolios comparables" subtitle="Retorno y correlación del período" />
          <div className="comparison-list">
            {comparisons.map((item) => (
              <div className="comparison-row" key={item.name}>
                <div>
                  <strong>{item.name}</strong>
                  <span>{item.symbols}</span>
                </div>
                <div>
                  <strong className={classFor(item.returnPercent)}>{signedPercent(item.returnPercent)}</strong>
                  <span>{percent(item.correlation * 100, 0)} corr.</span>
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}

function PositionsView({
  positions,
  decomposition,
  categories,
  query,
  category,
  sort,
  onQueryChange,
  onCategoryChange,
  onSortChange
}: {
  positions: PositionView[];
  decomposition: CategoryView[];
  categories: string[];
  query: string;
  category: string;
  sort: Sort;
  onQueryChange: (value: string) => void;
  onCategoryChange: (value: string) => void;
  onSortChange: (value: Sort) => void;
}) {
  const [openGroups, setOpenGroups] = useState<Set<string>>(
    () => new Set(decomposition[0] ? [decomposition[0].category] : [])
  );
  const stopRows = [...positions]
    .sort((left, right) => {
      const priorityOrder = { review: 0, watch: 1, normal: 2 };
      const byPriority = priorityOrder[left.stopLoss.priority] - priorityOrder[right.stopLoss.priority];
      return byPriority || right.stopLoss.valueAtRisk - left.stopLoss.valueAtRisk;
    })
    .slice(0, 8);

  function toggleGroup(group: string) {
    setOpenGroups((current) => {
      const next = new Set(current);
      if (next.has(group)) next.delete(group);
      else next.add(group);
      return next;
    });
  }

  return (
    <div className="view-stack">
      <section className="panel stops-panel">
        <PanelHeader
          title="Stops sugeridos"
          subtitle="Niveles calculados con volatilidad reciente y proteccion de ganancias"
          control={<Siren size={17} className="panel-heading-icon" />}
        />
        <div className="table-scroll">
          <table className="data-table stops-table">
            <thead>
              <tr>
                <th>Instrumento</th>
                <th>Precio actual</th>
                <th>Stop sugerido</th>
                <th>Distancia</th>
                <th>Riesgo nominal</th>
                <th>Riesgo %</th>
                <th>Regla</th>
                <th>Prioridad</th>
              </tr>
            </thead>
            <tbody>
              {stopRows.map((position) => (
                <tr key={`stop-${position.symbol}`}>
                  <td>
                    <div className="instrument-cell">
                      <SymbolMark symbol={position.symbol} small />
                      <div><strong>{position.symbol}</strong><span>{position.name}</span></div>
                    </div>
                  </td>
                  <td>{money(position.price)}</td>
                  <td><strong>{money(position.stopLoss.price)}</strong></td>
                  <td>{percent(position.stopLoss.distancePercent, 1)}</td>
                  <td className="negative">{signedMoney(-position.stopLoss.valueAtRisk)}</td>
                  <td className="negative">{percent(position.stopLoss.valueAtRiskPercent, 1)}</td>
                  <td>{position.stopLoss.rule}</td>
                  <td><span className={`priority-pill ${position.stopLoss.priority}`}>{stopPriorityLabel(position.stopLoss.priority)}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel category-panel">
        <PanelHeader title="Descomposición" subtitle="Totales por categoría de activo" />
        <div className="table-scroll">
          <table className="data-table category-table">
            <thead>
              <tr>
                <th>Categoría</th>
                <th>Activos</th>
                <th>Unidades</th>
                <th>Valor compra</th>
                <th>Valor actual</th>
                <th>P&amp;L diario</th>
                <th>P&amp;L diario %</th>
                <th>P&amp;L acum.</th>
                <th>P&amp;L acum. %</th>
              </tr>
            </thead>
            <tbody>
              {decomposition.map((row) => {
                const open = openGroups.has(row.category);
                return [
                  <tr className="category-group-row" key={row.category}>
                    <td>
                      <button
                        type="button"
                        className={`group-toggle ${open ? "open" : ""}`}
                        onClick={() => toggleGroup(row.category)}
                        aria-expanded={open}
                      >
                        <ChevronDown size={15} />
                        <strong>{row.category}</strong>
                      </button>
                    </td>
                    <td>{row.count}</td>
                    <td>{formatNumber(row.units)}</td>
                    <td>{row.cost === null ? "-" : money(row.cost)}</td>
                    <td><strong>{money(row.value)}</strong></td>
                    <td className={classFor(row.dayChange)}>{signedMoney(row.dayChange)}</td>
                    <td className={classFor(row.dayChangePercent)}>{signedPercent(row.dayChangePercent)}</td>
                    <td className={classFor(row.pnl ?? 0)}>{row.pnl === null ? "-" : signedMoney(row.pnl)}</td>
                    <td className={classFor(row.pnlPercent ?? 0)}>
                      {row.pnlPercent === null ? "-" : signedPercent(row.pnlPercent)}
                    </td>
                  </tr>,
                  ...(open ? row.positions.map((position) => (
                    <tr className="category-position-row" key={`${row.category}-${position.symbol}`}>
                      <td>
                        <div className="instrument-cell grouped-instrument">
                          <SymbolMark symbol={position.symbol} small />
                          <div><strong>{position.symbol}</strong><span>{position.name}</span></div>
                        </div>
                      </td>
                      <td>1</td>
                      <td>{formatNumber(position.quantity)}</td>
                      <td>{position.cost === null ? "-" : money(position.cost)}</td>
                      <td><strong>{money(position.value)}</strong></td>
                      <td className={classFor(position.dayChange)}>{signedMoney(position.dayChange)}</td>
                      <td className={classFor(position.dayChangePercent)}>{signedPercent(position.dayChangePercent)}</td>
                      <td className={classFor(position.pnl ?? 0)}>{position.pnl === null ? "-" : signedMoney(position.pnl)}</td>
                      <td className={classFor(position.pnlPercent ?? 0)}>{position.pnlPercent === null ? "-" : signedPercent(position.pnlPercent)}</td>
                    </tr>
                  )) : [])
                ];
              })}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel positions-panel">
        <div className="positions-header">
          <div>
            <h2>Posiciones</h2>
            <span>{positions.length} instrumentos</span>
          </div>
          <div className="filters">
            <label className="search-field">
              <Search size={15} />
              <input
                type="search"
                value={query}
                onChange={(event) => onQueryChange(event.target.value)}
                placeholder="Buscar símbolo"
                aria-label="Buscar posición"
              />
            </label>
            <select value={category} onChange={(event) => onCategoryChange(event.target.value)} aria-label="Categoría">
              <option value="all">Todas las categorías</option>
              {categories.map((item) => (
                <option value={item} key={item}>{item}</option>
              ))}
            </select>
            <select value={sort} onChange={(event) => onSortChange(event.target.value as Sort)} aria-label="Ordenar por">
              <option value="value">Mayor valor</option>
              <option value="day">Cambio diario</option>
              <option value="return">Retorno total</option>
              <option value="symbol">Símbolo A-Z</option>
            </select>
          </div>
        </div>

        <div className="table-scroll desktop-positions">
          <table className="data-table positions-table">
            <thead>
              <tr>
                <th>Instrumento</th>
                <th>Cantidad</th>
                <th>Precio</th>
                <th>Cambio precio</th>
                <th>Valor actual</th>
                <th>Peso</th>
                <th>Precio compra</th>
                <th>Stop sugerido</th>
                <th>P&amp;L diario</th>
                <th>P&amp;L acum.</th>
              </tr>
            </thead>
            <tbody>
              {positions.map((position) => (
                <tr key={position.symbol}>
                  <td>
                    <div className="instrument-cell">
                      <SymbolMark symbol={position.symbol} small />
                      <div>
                        <strong>{position.symbol}</strong>
                        <span>{position.name}</span>
                      </div>
                    </div>
                  </td>
                  <td>{formatNumber(position.quantity)}</td>
                  <td>{money(position.price)}</td>
                  <td className={classFor(position.dayChangePercent)}>{signedPercent(position.dayChangePercent)}</td>
                  <td><strong>{money(position.value)}</strong></td>
                  <td>{percent(position.weight, 1)}</td>
                  <td>{position.cost === null ? "-" : money(position.cost / position.quantity)}</td>
                  <td>
                    <strong>{money(position.stopLoss.price)}</strong>
                    <span>{percent(position.stopLoss.distancePercent, 1)}</span>
                  </td>
                  <td className={classFor(position.dayChange)}>
                    <strong>{signedMoney(position.dayChange)}</strong>
                    <span>{signedPercent(position.dayChangePercent)}</span>
                  </td>
                  <td className={classFor(position.pnl ?? 0)}>
                    <strong>{position.pnl === null ? "-" : signedMoney(position.pnl)}</strong>
                    <span>{position.pnlPercent === null ? "" : signedPercent(position.pnlPercent)}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="mobile-positions">
          {positions.map((position) => (
            <article className="position-card" key={position.symbol}>
              <div className="position-card-head">
                <div className="instrument-cell">
                  <SymbolMark symbol={position.symbol} small />
                  <div>
                    <strong>{position.symbol}</strong>
                    <span>{position.name}</span>
                  </div>
                </div>
                <div>
                  <strong>{money(position.value)}</strong>
                  <span>{percent(position.weight, 1)} del total</span>
                </div>
              </div>
              <div className="position-card-stats">
                <span>Precio<strong>{money(position.price)}</strong></span>
                <span>Stop<strong>{money(position.stopLoss.price)}</strong></span>
                <span>Hoy<strong className={classFor(position.dayChange)}>{signedMoney(position.dayChange)}</strong></span>
                <span>Total<strong className={classFor(position.pnl ?? 0)}>{position.pnl === null ? "-" : signedMoney(position.pnl)}</strong></span>
              </div>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}

function NewsView({
  news,
  loading,
  error,
  onRetry
}: {
  news: NewsResponse | null;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
}) {
  if (loading && !news) {
    return (
      <div className="news-loading">
        <RefreshCw size={20} className="spinning" />
        <strong>Actualizando noticias y calendario</strong>
        <span>Consultando las posiciones y el contexto de mercado</span>
      </div>
    );
  }

  if (error && !news) {
    return (
      <div className="news-error">
        <strong>{error}</strong>
        <button type="button" onClick={onRetry}><RefreshCw size={14} /> Reintentar</button>
      </div>
    );
  }

  if (!news) return null;

  return (
    <div className="view-stack news-view">
      <section className="panel news-agenda-panel">
        <PanelHeader
          title="Próximos eventos"
          subtitle="Earnings y fechas ex-dividendo de tus posiciones"
          control={<span className="as-of-label"><CalendarDays size={14} /> Próximos 9 días</span>}
        />
        {news.upcoming.length ? (
          <div className="event-strip">
            {news.upcoming.map((event) => (
              <a href={event.url} target="_blank" rel="noreferrer" className="event-item" key={event.id}>
                <span className={`event-icon ${event.type}`}>
                  {event.type === "earnings" ? "E" : "D"}
                </span>
                <div>
                  <strong>{event.title}</strong>
                  <span>{longNewsDate(event.date)} · {event.detail}</span>
                </div>
                <ExternalLink size={14} />
              </a>
            ))}
          </div>
        ) : <EmptyNews message="No hay earnings ni fechas ex-dividendo confirmadas para los próximos días." />}
      </section>

      {news.warnings?.length ? <div className="warning-banner">{news.warnings.join(" ")}</div> : null}

      <div className="news-grid">
        <section className="panel portfolio-news-panel">
          <PanelHeader title="Tus posiciones" subtitle="Información relevante del último mes" />
          <div className="company-news-list">
            {news.portfolio.map((group, index) => (
              <details className="company-news-group" key={group.symbol} open={index === 0}>
                <summary>
                  <SymbolMark symbol={group.symbol} small />
                  <strong>{group.symbol}</strong>
                  <span>{group.articles.length ? `${group.articles.length} noticias` : "Sin novedades relevantes"}</span>
                  <ChevronDown size={16} />
                </summary>
                <div className="company-article-list">
                  {group.articles.length ? group.articles.map((article) => (
                    <NewsArticleRow article={article} key={article.id} />
                  )) : <EmptyNews message="No se encontraron novedades recientes para esta posición." compact />}
                </div>
              </details>
            ))}
          </div>
        </section>

        <section className="panel market-news-panel">
          <PanelHeader
            title="Mercados globales"
            subtitle="Noticias financieras relevantes de la última semana"
            control={<Globe2 size={17} className="panel-heading-icon" />}
          />
          <div className="market-article-list">
            {news.market.length ? news.market.map((article) => (
              <NewsArticleRow article={article} key={article.id} />
            )) : <EmptyNews message="No se pudieron obtener noticias de mercado recientes." />}
          </div>
        </section>
      </div>
    </div>
  );
}

function NewsArticleRow({ article }: { article: NewsResponse["market"][number] }) {
  return (
    <a className="news-article" href={article.url} target="_blank" rel="noreferrer">
      <div className="news-article-meta">
        <span className={`news-kind kind-${article.kind}`}>{newsKindLabel(article.kind)}</span>
        <span>{article.source}</span>
        <span>{relativeNewsDate(article.publishedAt)}</span>
      </div>
      <strong>{article.title}</strong>
      <ExternalLink size={14} />
    </a>
  );
}

function EmptyNews({ message, compact = false }: { message: string; compact?: boolean }) {
  return <div className={`empty-news ${compact ? "compact" : ""}`}>{message}</div>;
}

function PerformanceChart({
  data,
  large = false
}: {
  data: Array<{ date: string; portfolio: number; benchmark?: number }>;
  large?: boolean;
}) {
  return (
    <div className={`performance-chart ${large ? "large" : ""}`}>
      <ResponsiveContainer>
        <ReLineChart data={data} margin={{ top: 10, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="#e7ebe9" vertical={false} />
          <XAxis
            dataKey="date"
            tickLine={false}
            axisLine={false}
            minTickGap={42}
            tickFormatter={shortDate}
            tick={{ fill: "#77817d", fontSize: 11 }}
          />
          <YAxis
            tickFormatter={(value) => `${value.toFixed(0)}%`}
            tickLine={false}
            axisLine={false}
            width={44}
            tick={{ fill: "#77817d", fontSize: 11 }}
          />
          <Tooltip
            labelFormatter={(value) => longDate(String(value))}
            formatter={(value: number, name: string) => [
              signedPercent(value),
              name === "portfolio" ? "Portafolio" : "Benchmark"
            ]}
            contentStyle={{ borderRadius: 6, borderColor: "#d9dfdc", boxShadow: "0 8px 24px rgba(25, 38, 33, .1)" }}
          />
          <Line
            type="monotone"
            dataKey="portfolio"
            stroke="#136f63"
            strokeWidth={2.5}
            dot={false}
            activeDot={{ r: 4 }}
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="benchmark"
            stroke="#2f6fbb"
            strokeWidth={2}
            dot={false}
            strokeDasharray="5 4"
            isAnimationActive={false}
          />
        </ReLineChart>
      </ResponsiveContainer>
    </div>
  );
}

function RangeControl({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return (
    <div className="range-control" aria-label="Rango de tiempo">
      {ranges.map((item) => (
        <button
          type="button"
          className={value === item.value ? "active" : ""}
          onClick={() => onChange(item.value)}
          key={item.value}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}

function TabButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return <button type="button" className={active ? "active" : ""} onClick={onClick}>{children}</button>;
}

function PanelHeader({
  title,
  subtitle,
  control
}: {
  title: string;
  subtitle: string;
  control?: React.ReactNode;
}) {
  return (
    <div className="panel-header">
      <div>
        <h2>{title}</h2>
        <span>{subtitle}</span>
      </div>
      {control}
    </div>
  );
}

function SummaryMetric({
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
    <div className="summary-metric">
      <span>{label}</span>
      <strong className={trend === undefined ? "" : classFor(trend)}>{value}</strong>
      <small className={trend === undefined ? "" : classFor(trend)}>{detail}</small>
    </div>
  );
}

function Stat({ label, value, trend }: { label: string; value: string; trend?: number }) {
  return (
    <div className="stat">
      <span>{label}</span>
      <strong className={trend === undefined ? "" : classFor(trend)}>{value}</strong>
    </div>
  );
}

function Trend({ value, percentValue, label }: { value: number; percentValue: number; label: string }) {
  const Icon = value >= 0 ? ArrowUpRight : ArrowDownRight;
  return (
    <div className={`trend ${classFor(value)}`}>
      <Icon size={15} />
      <strong>{signedMoney(value)}</strong>
      <span>({signedPercent(percentValue)}) {label}</span>
    </div>
  );
}

function ChartLegend({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="chart-legend">
      <span style={{ background: color }} />
      <div>
        <small>{label}</small>
        <strong className={classFor(value)}>{signedPercent(value)}</strong>
      </div>
    </div>
  );
}

function HealthMetric({
  label,
  value,
  fill,
  threshold
}: {
  label: string;
  value: string;
  fill: number;
  threshold: number;
}) {
  return (
    <div className="health-row">
      <div><span>{label}</span><strong>{value}</strong></div>
      <div className="health-track">
        <span style={{ width: `${Math.min(fill, 100)}%` }} />
        <i style={{ left: `${Math.min(threshold, 100)}%` }} />
      </div>
    </div>
  );
}

function SymbolMark({ symbol, small = false }: { symbol: string; small?: boolean }) {
  return <span className={`symbol-mark ${small ? "small" : ""}`}>{symbol.slice(0, 2)}</span>;
}

function LoadingState() {
  return (
    <div className="loading-state">
      <RefreshCw size={20} className="spinning" />
      <strong>Sincronizando el portafolio</strong>
      <span>Obteniendo posiciones y precios de mercado</span>
    </div>
  );
}

function riskMetrics(points: Array<{ portfolio: number }>) {
  const returns = dailyReturns(points);
  const mean = returns.length ? returns.reduce((sum, value) => sum + value, 0) / returns.length : 0;
  const variance = returns.length
    ? returns.reduce((sum, value) => sum + (value - mean) ** 2, 0) / returns.length
    : 0;
  let peak = 100;
  let maxDrawdown = 0;
  for (const point of points) {
    const index = 100 + point.portfolio;
    peak = Math.max(peak, index);
    maxDrawdown = Math.min(maxDrawdown, peak ? (index / peak - 1) * 100 : 0);
  }
  return {
    volatility: Math.sqrt(variance) * Math.sqrt(252) * 100,
    maxDrawdown,
    positiveDays: returns.length ? (returns.filter((value) => value > 0).length / returns.length) * 100 : 0
  };
}

function money(value: number) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(value);
}

function compactMoney(value: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    notation: "compact",
    maximumFractionDigits: 1
  }).format(value);
}

function signedMoney(value: number) {
  const formatted = money(Math.abs(value));
  return value > 0 ? `+${formatted}` : value < 0 ? `-${formatted}` : formatted;
}

function percent(value: number, digits = 2) {
  return `${value.toFixed(digits)}%`;
}

function signedPercent(value: number, digits = 2) {
  const formatted = `${Math.abs(value).toFixed(digits)}%`;
  return value > 0 ? `+${formatted}` : value < 0 ? `-${formatted}` : formatted;
}

function formatNumber(value: number) {
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 4 }).format(value);
}

function time(value: string) {
  return new Intl.DateTimeFormat("es-UY", { hour: "2-digit", minute: "2-digit" }).format(new Date(value));
}

function shortDate(value: string) {
  return new Intl.DateTimeFormat("es-UY", { month: "short", day: "numeric" }).format(new Date(`${value}T12:00:00`));
}

function longDate(value: string) {
  return new Intl.DateTimeFormat("es-UY", { year: "numeric", month: "short", day: "numeric" }).format(new Date(`${value}T12:00:00`));
}

function longNewsDate(value: string) {
  return new Intl.DateTimeFormat("es-UY", { weekday: "short", month: "short", day: "numeric" })
    .format(new Date(`${value}T12:00:00`));
}

function relativeNewsDate(value: string) {
  const days = Math.max(0, Math.round((Date.now() - new Date(value).getTime()) / 86_400_000));
  if (days === 0) return "Hoy";
  if (days === 1) return "Ayer";
  return `Hace ${days} días`;
}

function newsKindLabel(kind: NewsKind) {
  const labels: Record<NewsKind, string> = {
    earnings: "Resultados",
    dividend: "Dividendos",
    guidance: "Perspectivas",
    analyst: "Analistas",
    deal: "Operaciones",
    regulation: "Regulación",
    macro: "Macroeconomía",
    geopolitics: "Geopolítica",
    markets: "Mercados",
    company: "Compañía"
  };
  return labels[kind];
}

function stopPriorityLabel(priority: PositionView["stopLoss"]["priority"]) {
  const labels = {
    review: "Revisar",
    watch: "Vigilar",
    normal: "Normal"
  };
  return labels[priority];
}

function rangeLabel(value: string) {
  return ranges.find((item) => item.value === value)?.label ?? value;
}

function benchmarkName(symbol: string) {
  const labels: Record<string, string> = {
    SPY: "S&P 500",
    QQQ: "Nasdaq 100",
    QUAL: "US Quality",
    EFA: "Mercados desarrollados",
    EEM: "Mercados emergentes"
  };
  return labels[symbol] ?? symbol;
}

function classFor(value: number) {
  if (value > 0) return "positive";
  if (value < 0) return "negative";
  return "neutral";
}

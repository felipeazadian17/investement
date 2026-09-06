import type { Holding, MarketSeries, PricePoint, SimilarPortfolio } from "./types";

export type PositionView = {
  symbol: string;
  name: string;
  quantity: number;
  assetType: string;
  style: string;
  category: string;
  benchmark: string;
  price: number;
  value: number;
  cost: number | null;
  pnl: number | null;
  pnlPercent: number | null;
  weight: number;
  dayChange: number;
  dayChangePercent: number;
  stopLoss: StopLossView;
};

export type PortfolioView = {
  totalValue: number;
  investedValue: number;
  cash: number;
  cashWeight: number;
  totalCost: number | null;
  totalPnl: number | null;
  totalPnlPercent: number | null;
  dayChange: number;
  dayChangePercent: number;
  positions: PositionView[];
  allocation: Array<{ symbol: string; value: number; weight: number }>;
  performance: Array<{ date: string; portfolio: number; benchmark?: number }>;
  decomposition: CategoryView[];
};

export type StopLossView = {
  price: number;
  valueAtRisk: number;
  valueAtRiskPercent: number;
  distancePercent: number;
  rule: string;
  priority: "review" | "watch" | "normal";
};

export type CategoryView = {
  category: string;
  count: number;
  units: number;
  cost: number | null;
  value: number;
  dayChange: number;
  dayChangePercent: number;
  pnl: number | null;
  pnlPercent: number | null;
  positions: PositionView[];
};

export function buildPortfolioView(
  holdings: Holding[],
  market: MarketSeries[],
  benchmark?: MarketSeries,
  cash = 0
): PortfolioView {
  const bySymbol = new Map(market.map((item) => [item.symbol, item]));
  const rawPositions = holdings.map((holding) => {
    const series = bySymbol.get(holding.symbol);
    const price = series?.price ?? 0;
    const value = holding.quantity * price;
    const cost = holding.costBasis === undefined ? null : holding.quantity * holding.costBasis;
    const costPerShare = holding.costBasis;
    const stopLoss = buildStopLoss({
      price,
      quantity: holding.quantity,
      costBasis: costPerShare,
      assetType: holding.assetType ?? inferAssetType(holding.symbol),
      style: holding.style ?? inferStyle(holding.symbol),
      history: series?.history ?? []
    });
    return {
      symbol: holding.symbol,
      name: holding.name ?? holding.symbol,
      quantity: holding.quantity,
      assetType: holding.assetType ?? inferAssetType(holding.symbol),
      style: holding.style ?? inferStyle(holding.symbol),
      category: categoryFor(holding),
      benchmark: holding.benchmark ?? benchmarkFor(holding),
      price,
      value,
      cost,
      pnl: cost === null ? null : value - cost,
      pnlPercent: cost === null || cost === 0 ? null : (value / cost - 1) * 100,
      weight: 0,
      dayChange: holding.quantity * (price - (series?.previousClose ?? price)),
      dayChangePercent: series?.changePercent ?? 0,
      stopLoss
    };
  });
  const investedValue = rawPositions.reduce((sum, item) => sum + item.value, 0);
  const totalValue = investedValue + cash;
  const hasCompleteCost = rawPositions.length > 0 && rawPositions.every((item) => item.cost !== null);
  const totalCost = hasCompleteCost
    ? rawPositions.reduce((sum, item) => sum + (item.cost ?? 0), 0)
    : null;
  const positions = rawPositions.map((position) => ({
    ...position,
    weight: totalValue ? (position.value / totalValue) * 100 : 0
  }));
  const dayChange = positions.reduce((sum, item) => sum + item.dayChange, 0);
  const previousValue = totalValue - dayChange;

  return {
    totalValue,
    investedValue,
    cash,
    cashWeight: totalValue ? (cash / totalValue) * 100 : 0,
    totalCost,
    totalPnl: totalCost === null ? null : investedValue - totalCost,
    totalPnlPercent:
      totalCost === null || totalCost === 0 ? null : (investedValue / totalCost - 1) * 100,
    dayChange,
    dayChangePercent: previousValue ? (dayChange / previousValue) * 100 : 0,
    positions,
    allocation: positions.map(({ symbol, value, weight }) => ({ symbol, value, weight })),
    performance: buildPerformance(holdings, market, benchmark, cash),
    decomposition: buildDecomposition(positions)
  };
}

export function buildCompositeBenchmark(holdings: Holding[], market: MarketSeries[]) {
  const bySymbol = new Map(market.map((item) => [item.symbol, item]));
  const weightedBenchmarks = holdings.map((holding) => ({
    symbol: holding.benchmark ?? benchmarkFor(holding),
    weight: holding.quantity * (bySymbol.get(holding.symbol)?.price ?? 0)
  }));
  const byBenchmark = new Map<string, number>();
  for (const item of weightedBenchmarks) {
    byBenchmark.set(item.symbol, (byBenchmark.get(item.symbol) ?? 0) + item.weight);
  }
  return buildWeightedPerformance(
    Array.from(byBenchmark.entries()).map(([symbol, weight]) => ({ symbol, weight })),
    market
  );
}

export function buildBenchmarkMix(holdings: Holding[], market: MarketSeries[]) {
  const bySymbol = new Map(market.map((item) => [item.symbol, item]));
  const groups = new Map<string, number>();
  for (const holding of holdings) {
    const symbol = holding.benchmark ?? benchmarkFor(holding);
    const value = holding.quantity * (bySymbol.get(holding.symbol)?.price ?? 0);
    groups.set(symbol, (groups.get(symbol) ?? 0) + value);
  }
  const total = Array.from(groups.values()).reduce((sum, value) => sum + value, 0);
  return Array.from(groups.entries())
    .map(([symbol, value]) => ({ symbol, value, weight: total ? (value / total) * 100 : 0 }))
    .sort((left, right) => right.value - left.value);
}

export function buildSimilarPerformance(portfolio: SimilarPortfolio, market: MarketSeries[]) {
  return buildWeightedPerformance(
    portfolio.holdings.map((holding) => ({ symbol: holding.symbol, weight: holding.quantity })),
    market
  );
}

export function correlation(a: number[], b: number[]) {
  const count = Math.min(a.length, b.length);
  if (count < 3) return 0;
  const left = a.slice(-count);
  const right = b.slice(-count);
  const meanA = average(left);
  const meanB = average(right);
  let numerator = 0;
  let varianceA = 0;
  let varianceB = 0;
  for (let index = 0; index < count; index += 1) {
    const da = left[index] - meanA;
    const db = right[index] - meanB;
    numerator += da * db;
    varianceA += da * da;
    varianceB += db * db;
  }
  return varianceA && varianceB ? numerator / Math.sqrt(varianceA * varianceB) : 0;
}

export function dailyReturns(points: Array<{ portfolio: number }>) {
  return points.slice(1).map((point, index) => {
    const previousIndex = 100 + points[index].portfolio;
    return previousIndex ? (100 + point.portfolio) / previousIndex - 1 : 0;
  });
}

function buildPerformance(
  holdings: Holding[],
  market: MarketSeries[],
  benchmark?: MarketSeries,
  cash = 0
) {
  const bySymbol = new Map(market.map((item) => [item.symbol, item]));
  const dates = commonDates(holdings.map((holding) => bySymbol.get(holding.symbol)?.history ?? []));
  const raw = dates.map((date) => {
    const value = cash + holdings.reduce((sum, holding) => {
      const point = bySymbol.get(holding.symbol)?.history.find((item) => item.date === date);
      return sum + holding.quantity * (point?.close ?? 0);
    }, 0);
    return { date, value };
  });
  const base = raw[0]?.value || 1;
  const benchmarkBase = benchmark?.history.find((point) => point.date === raw[0]?.date)?.close || 1;

  return raw.map((point) => {
    const benchmarkPoint = benchmark?.history.find((item) => item.date === point.date);
    return {
      date: point.date,
      portfolio: (point.value / base - 1) * 100,
      benchmark: benchmarkPoint ? (benchmarkPoint.close / benchmarkBase - 1) * 100 : undefined
    };
  });
}

function buildWeightedPerformance(
  weights: Array<{ symbol: string; weight: number }>,
  market: MarketSeries[]
) {
  const bySymbol = new Map(market.map((item) => [item.symbol, item]));
  const active = weights.filter(
    (item) => item.weight > 0 && (bySymbol.get(item.symbol)?.history.length ?? 0) > 0
  );
  const dates = commonDates(active.map((item) => bySymbol.get(item.symbol)?.history ?? []));
  const totalWeight = active.reduce((sum, item) => sum + item.weight, 0);
  if (!dates.length || !totalWeight) return [];
  const firstDate = dates[0];
  const bases = new Map(
    active.map((item) => [
      item.symbol,
      bySymbol.get(item.symbol)?.history.find((point) => point.date === firstDate)?.close ?? 1
    ])
  );

  return dates.map((date) => ({
    date,
    portfolio: active.reduce((sum, item) => {
      const close = bySymbol.get(item.symbol)?.history.find((point) => point.date === date)?.close ?? 0;
      const base = bases.get(item.symbol) ?? 1;
      return sum + (item.weight / totalWeight) * (close / base - 1) * 100;
    }, 0)
  }));
}

function buildDecomposition(positions: PositionView[]): CategoryView[] {
  const groups = new Map<string, PositionView[]>();
  for (const position of positions) {
    const list = groups.get(position.category) ?? [];
    list.push(position);
    groups.set(position.category, list);
  }
  return Array.from(groups.entries())
    .map(([category, items]) => {
      const value = items.reduce((sum, item) => sum + item.value, 0);
      const costValues = items.map((item) => item.cost).filter((item): item is number => item !== null);
      const cost = costValues.length === items.length ? costValues.reduce((sum, item) => sum + item, 0) : null;
      const dayChange = items.reduce((sum, item) => sum + item.dayChange, 0);
      const previousValue = value - dayChange;
      return {
        category,
        count: items.length,
        units: items.reduce((sum, item) => sum + item.quantity, 0),
        cost,
        value,
        dayChange,
        dayChangePercent: previousValue ? (dayChange / previousValue) * 100 : 0,
        pnl: cost === null ? null : value - cost,
        pnlPercent: cost === null || cost === 0 ? null : (value / cost - 1) * 100,
        positions: items
      };
    })
    .sort((left, right) => right.value - left.value);
}

function buildStopLoss({
  price,
  quantity,
  costBasis,
  assetType,
  style,
  history
}: {
  price: number;
  quantity: number;
  costBasis?: number;
  assetType: string;
  style: string;
  history: PricePoint[];
}): StopLossView {
  if (!price || quantity <= 0) {
    return {
      price: 0,
      valueAtRisk: 0,
      valueAtRiskPercent: 0,
      distancePercent: 0,
      rule: "Sin precio",
      priority: "review"
    };
  }

  const floor = stopFloor(assetType, style);
  const ceiling = stopCeiling(assetType, style);
  const dailyVolatility = realizedDailyVolatility(history.slice(-63));
  const volatilityBuffer = dailyVolatility ? dailyVolatility * 2.8 * 100 : floor;
  const buffer = clamp(volatilityBuffer, floor, ceiling);
  const trailingStop = price * (1 - buffer / 100);
  const protectedCost = costBasis && price / costBasis - 1 > 0.18 ? costBasis * 1.03 : 0;
  const stopPrice = Math.min(price * 0.98, Math.max(trailingStop, protectedCost));
  const valueAtRisk = Math.max(0, (price - stopPrice) * quantity);
  const value = price * quantity;
  const valueAtRiskPercent = value ? (valueAtRisk / value) * 100 : 0;
  const distancePercent = price ? (price / stopPrice - 1) * 100 : 0;

  return {
    price: stopPrice,
    valueAtRisk,
    valueAtRiskPercent,
    distancePercent,
    rule: `${Math.round(buffer)}% trail`,
    priority: distancePercent < 4 || valueAtRiskPercent > 18 ? "review" : distancePercent < 8 ? "watch" : "normal"
  };
}

function realizedDailyVolatility(history: PricePoint[]) {
  const returns = history.slice(1).flatMap((point, index) => {
    const previous = history[index]?.close;
    return previous ? [point.close / previous - 1] : [];
  });
  if (returns.length < 10) return 0;
  const mean = average(returns);
  const variance = returns.reduce((sum, value) => sum + (value - mean) ** 2, 0) / returns.length;
  return Math.sqrt(variance);
}

function stopFloor(assetType: string, style: string) {
  if (assetType === "etf" || assetType === "mutual_fund") return 7;
  if (style === "dividend" || style === "value") return 9;
  if (style === "growth" || style === "foreign") return 12;
  return 10;
}

function stopCeiling(assetType: string, style: string) {
  if (assetType === "etf" || assetType === "mutual_fund") return 14;
  if (style === "growth" || style === "foreign") return 22;
  return 18;
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

function categoryFor(holding: Holding) {
  const assetType = holding.assetType ?? inferAssetType(holding.symbol);
  if (assetType === "stock") return `Acciones · ${styleLabel(holding.style ?? inferStyle(holding.symbol))}`;
  if (assetType === "etf") return "ETFs";
  if (assetType === "mutual_fund") return "Fondos mutuos";
  if (assetType === "crypto") return "Cripto";
  return title(assetType);
}

function styleLabel(style: string) {
  const labels: Record<string, string> = {
    value: "Value",
    growth: "Growth",
    dividend: "Dividendos",
    foreign: "Internacional",
    blend: "Blend"
  };
  return labels[style] ?? title(style);
}

function inferAssetType(symbol: string) {
  if (new Set(["EEM", "EFA", "QUAL", "SPY", "QQQ", "MOAT", "VTI", "VUG", "SCHG"]).has(symbol)) {
    return "etf";
  }
  return "stock";
}

function inferStyle(symbol: string) {
  if (new Set(["MELI", "GLOB", "WTW", "EEM", "EFA"]).has(symbol)) return "foreign";
  if (new Set(["NVDA", "EXE"]).has(symbol)) return "growth";
  if (new Set(["AFL", "FE"]).has(symbol)) return "dividend";
  if (new Set(["CTSH", "INCY", "PYPL", "REGN", "ERIE"]).has(symbol)) return "value";
  return "blend";
}

function benchmarkFor(holding: Holding) {
  const assetType = holding.assetType ?? inferAssetType(holding.symbol);
  if (assetType === "etf") return holding.symbol;
  if (holding.symbol === "MELI" || holding.symbol === "GLOB") return "EEM";
  if (holding.symbol === "WTW") return "EFA";
  return "SPY";
}

function title(value: string) {
  return value.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function commonDates(series: PricePoint[][]) {
  if (!series.length) return [];
  const [first, ...rest] = series;
  return first
    .map((point) => point.date)
    .filter((date) => rest.every((items) => items.some((point) => point.date === date)));
}

function average(values: number[]) {
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

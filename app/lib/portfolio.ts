import type { Holding, MarketSeries, PricePoint, SimilarPortfolio } from "./types";

export type PositionView = {
  symbol: string;
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
};

export type PortfolioView = {
  totalValue: number;
  totalCost: number;
  totalPnl: number;
  totalPnlPercent: number;
  dayChange: number;
  positions: PositionView[];
  allocation: Array<{ symbol: string; value: number; weight: number }>;
  performance: Array<{ date: string; portfolio: number; benchmark?: number }>;
  decomposition: CategoryView[];
};

export type CategoryView = {
  category: string;
  count: number;
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
  benchmark?: MarketSeries
): PortfolioView {
  const bySymbol = new Map(market.map((item) => [item.symbol, item]));
  const rawPositions = holdings.map((holding) => {
    const series = bySymbol.get(holding.symbol);
    const price = series?.price ?? 0;
    const value = holding.quantity * price;
    const cost = holding.costBasis === undefined ? null : holding.quantity * holding.costBasis;
    return {
      symbol: holding.symbol,
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
      dayChange: value * ((series?.changePercent ?? 0) / 100),
      dayChangePercent: series?.changePercent ?? 0
    };
  });
  const totalValue = rawPositions.reduce((sum, item) => sum + item.value, 0);
  const totalCost = rawPositions.reduce((sum, item) => sum + (item.cost ?? 0), 0);
  const positions = rawPositions.map((position) => ({
    ...position,
    weight: totalValue ? (position.value / totalValue) * 100 : 0
  }));

  return {
    totalValue,
    totalCost,
    totalPnl: totalValue - totalCost,
    totalPnlPercent: totalCost ? (totalValue / totalCost - 1) * 100 : 0,
    dayChange: positions.reduce((sum, item) => sum + item.dayChange, 0),
    positions,
    allocation: positions.map(({ symbol, value, weight }) => ({ symbol, value, weight })),
    performance: buildPerformance(holdings, market, benchmark),
    decomposition: buildDecomposition(positions)
  };
}

export function buildCompositeBenchmark(holdings: Holding[], market: MarketSeries[]) {
  const bySymbol = new Map(market.map((item) => [item.symbol, item]));
  const weightedBenchmarks = holdings.map((holding) => ({
    symbol: holding.benchmark ?? benchmarkFor(holding),
    weight: holding.quantity * (bySymbol.get(holding.symbol)?.price ?? 0)
  }));
  const total = weightedBenchmarks.reduce((sum, item) => sum + item.weight, 0);
  const byBenchmark = new Map<string, number>();
  for (const item of weightedBenchmarks) {
    byBenchmark.set(item.symbol, (byBenchmark.get(item.symbol) ?? 0) + item.weight);
  }
  const benchmarkHoldings = Array.from(byBenchmark.entries()).map(([symbol, value]) => ({
    symbol,
    quantity: total ? value / total : 0
  }));
  return buildPerformance(benchmarkHoldings, market);
}

export function buildSimilarPerformance(portfolio: SimilarPortfolio, market: MarketSeries[]) {
  return buildPerformance(portfolio.holdings, market);
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
  return points.slice(1).map((point, index) => point.portfolio / points[index].portfolio - 1);
}

function buildPerformance(holdings: Holding[], market: MarketSeries[], benchmark?: MarketSeries) {
  const bySymbol = new Map(market.map((item) => [item.symbol, item]));
  const dates = commonDates(holdings.map((holding) => bySymbol.get(holding.symbol)?.history ?? []));
  const raw = dates.map((date) => {
    const value = holdings.reduce((sum, holding) => {
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
      return {
        category,
        count: items.length,
        cost,
        value,
        dayChange,
        dayChangePercent: value ? (dayChange / value) * 100 : 0,
        pnl: cost === null ? null : value - cost,
        pnlPercent: cost === null || cost === 0 ? null : (value / cost - 1) * 100,
        positions: items
      };
    })
    .sort((left, right) => right.value - left.value);
}

function categoryFor(holding: Holding) {
  const assetType = holding.assetType ?? inferAssetType(holding.symbol);
  if (assetType === "stock") return `Stocks - ${holding.style ?? inferStyle(holding.symbol)}`;
  if (assetType === "etf") return "ETFs";
  if (assetType === "mutual_fund") return "Mutual funds";
  return title(assetType);
}

function inferAssetType(symbol: string) {
  if (new Set(["EEM", "EFA", "QUAL", "SPY", "QQQ", "MOAT", "VTI", "VUG", "SCHG"]).has(symbol)) {
    return "etf";
  }
  return "stock";
}

function inferStyle(symbol: string) {
  if (new Set(["MELI", "NVDA", "GLOB", "EXE"]).has(symbol)) return "growth";
  if (new Set(["AFL", "FE", "WTW"]).has(symbol)) return "dividend";
  if (new Set(["EEM", "EFA"]).has(symbol)) return "foreign";
  if (new Set(["CTSH", "INCY", "PYPL", "REGN", "ERIE"]).has(symbol)) return "value";
  return "blend";
}

function benchmarkFor(holding: Holding) {
  const assetType = holding.assetType ?? inferAssetType(holding.symbol);
  const style = holding.style ?? inferStyle(holding.symbol);
  if (assetType === "etf" && holding.symbol === "EEM") return "EEM";
  if (assetType === "etf" && holding.symbol === "EFA") return "EFA";
  if (style === "foreign") return "EFA";
  if (style === "growth") return "QQQ";
  if (style === "value" || style === "dividend") return "QUAL";
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

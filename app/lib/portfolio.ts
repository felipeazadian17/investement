import type { Holding, MarketSeries, PricePoint, SimilarPortfolio } from "./types";

export type PositionView = {
  symbol: string;
  quantity: number;
  price: number;
  value: number;
  cost: number | null;
  pnl: number | null;
  pnlPercent: number | null;
  weight: number;
  dayChange: number;
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
      price,
      value,
      cost,
      pnl: cost === null ? null : value - cost,
      pnlPercent: cost === null || cost === 0 ? null : (value / cost - 1) * 100,
      weight: 0,
      dayChange: value * ((series?.changePercent ?? 0) / 100)
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
    performance: buildPerformance(holdings, market, benchmark)
  };
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

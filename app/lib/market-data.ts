import type { MarketSeries } from "./types";

type YahooResult = {
  meta?: {
    regularMarketPrice?: number;
    chartPreviousClose?: number;
    previousClose?: number;
  };
  timestamp?: number[];
  indicators?: {
    quote?: Array<{ close?: Array<number | null> }>;
    adjclose?: Array<{ adjclose?: Array<number | null> }>;
  };
};

export async function fetchYahooSeries(symbol: string, range: string): Promise<MarketSeries> {
  const url = new URL(`https://query1.finance.yahoo.com/v8/finance/chart/${symbol}`);
  url.searchParams.set("range", range);
  url.searchParams.set("interval", "1d");
  url.searchParams.set("includePrePost", "false");
  url.searchParams.set("events", "div,splits");

  const response = await fetch(url, {
    headers: { Accept: "application/json", "User-Agent": "investement-dashboard/0.1" },
    cache: "no-store"
  });
  if (!response.ok) throw new Error(`Yahoo request failed for ${symbol}`);

  const payload = await response.json();
  const result = payload?.chart?.result?.[0] as YahooResult | undefined;
  if (!result) throw new Error(`Yahoo returned no chart data for ${symbol}`);

  const timestamps = result.timestamp ?? [];
  const closes = result.indicators?.adjclose?.[0]?.adjclose ?? result.indicators?.quote?.[0]?.close ?? [];
  const history = timestamps
    .map((timestamp, index) => ({
      date: new Date(timestamp * 1000).toISOString().slice(0, 10),
      close: closes[index]
    }))
    .filter((point): point is { date: string; close: number } => typeof point.close === "number");
  const price = result.meta?.regularMarketPrice ?? history.at(-1)?.close ?? 0;
  const previousClose =
    history.at(-2)?.close ?? result.meta?.previousClose ?? result.meta?.chartPreviousClose ?? price;

  return {
    symbol,
    price,
    previousClose,
    changePercent: previousClose ? (price / previousClose - 1) * 100 : 0,
    history
  };
}

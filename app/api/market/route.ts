import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

type YahooResult = {
  meta?: {
    regularMarketPrice?: number;
    chartPreviousClose?: number;
    previousClose?: number;
    currency?: string;
  };
  timestamp?: number[];
  indicators?: {
    quote?: Array<{ close?: Array<number | null> }>;
    adjclose?: Array<{ adjclose?: Array<number | null> }>;
  };
};

const allowedRanges = new Set(["1mo", "3mo", "6mo", "1y", "2y", "5y"]);
const symbolPattern = /^[A-Z0-9.^=-]{1,15}$/;

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const symbols = Array.from(
    new Set(
      (searchParams.get("symbols") ?? "")
        .split(",")
        .map((symbol) => symbol.trim().toUpperCase())
        .filter(Boolean)
    )
  );
  const range = searchParams.get("range") ?? "1y";

  if (!symbols.length || symbols.length > 30) {
    return NextResponse.json({ error: "Provide 1 to 30 symbols." }, { status: 400 });
  }
  if (!allowedRanges.has(range)) {
    return NextResponse.json({ error: "Unsupported range." }, { status: 400 });
  }
  if (symbols.some((symbol) => !symbolPattern.test(symbol))) {
    return NextResponse.json({ error: "Invalid symbol." }, { status: 400 });
  }

  const series = await Promise.all(symbols.map((symbol) => fetchYahooSeries(symbol, range)));

  return NextResponse.json(
    { asOf: new Date().toISOString(), series },
    {
      headers: {
        "Cache-Control": "s-maxage=60, stale-while-revalidate=300"
      }
    }
  );
}

async function fetchYahooSeries(symbol: string, range: string) {
  const url = new URL(`https://query1.finance.yahoo.com/v8/finance/chart/${symbol}`);
  url.searchParams.set("range", range);
  url.searchParams.set("interval", range === "1mo" ? "1d" : "1d");
  url.searchParams.set("includePrePost", "false");
  url.searchParams.set("events", "div,splits");

  const response = await fetch(url, {
    headers: {
      Accept: "application/json",
      "User-Agent": "investement-dashboard/0.1"
    },
    cache: "no-store"
  });

  if (!response.ok) {
    throw new Error(`Yahoo request failed for ${symbol}`);
  }

  const payload = await response.json();
  const result = payload?.chart?.result?.[0] as YahooResult | undefined;
  if (!result) {
    throw new Error(`Yahoo returned no chart data for ${symbol}`);
  }

  const timestamps = result.timestamp ?? [];
  const closes =
    result.indicators?.adjclose?.[0]?.adjclose ?? result.indicators?.quote?.[0]?.close ?? [];
  const history = timestamps
    .map((timestamp, index) => ({
      date: new Date(timestamp * 1000).toISOString().slice(0, 10),
      close: closes[index]
    }))
    .filter((point): point is { date: string; close: number } => typeof point.close === "number");

  const price = result.meta?.regularMarketPrice ?? history.at(-1)?.close ?? 0;
  // Yahoo's chartPreviousClose may be the first close of the selected chart range.
  // The penultimate daily observation is the reliable comparison for today's move.
  const previousClose =
    history.at(-2)?.close ?? result.meta?.previousClose ?? result.meta?.chartPreviousClose ?? price;
  const changePercent = previousClose ? (price / previousClose - 1) * 100 : 0;

  return {
    symbol,
    price,
    previousClose,
    changePercent,
    history
  };
}

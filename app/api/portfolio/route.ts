import crypto from "node:crypto";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { NextResponse } from "next/server";
import type { Holding, PortfolioConfig } from "../../lib/types";

export const dynamic = "force-dynamic";

const baseUrl = "https://api.snaptrade.com/api/v1";
const supportedKinds = new Set(["adr", "cef", "crypto", "etf", "mutualfund", "stock"]);

type SnapTradeAccount = {
  id?: string;
};

type SnapTradePosition = {
  cash_equivalent?: boolean;
  units?: number | string;
  currency?: string | { code?: string };
  instrument?: {
    kind?: string;
    symbol?: string;
    currency?: string | { code?: string };
  };
};

export async function GET() {
  const clientId = process.env.SNAPTRADE_CLIENT_ID?.trim();
  const consumerKey = process.env.SNAPTRADE_CONSUMER_KEY?.trim();

  if (clientId && consumerKey) {
    const holdings = await readSnapTradeHoldings(clientId, consumerKey);
    return NextResponse.json(
      {
        baseCurrency: process.env.PORTFOLIO_BASE_CURRENCY ?? "USD",
        benchmark: process.env.PORTFOLIO_BENCHMARK ?? "SPY",
        holdings,
        similarPortfolios: defaultSimilarPortfolios()
      },
      { headers: { "Cache-Control": "s-maxage=60, stale-while-revalidate=300" } }
    );
  }

  const local = await readLocalConfig();
  return NextResponse.json(local, {
    headers: { "Cache-Control": "no-store" }
  });
}

async function readSnapTradeHoldings(clientId: string, consumerKey: string) {
  const accounts = (await snapTradeGet("/accounts", clientId, consumerKey)) as SnapTradeAccount[];
  const quantities = new Map<string, number>();
  const baseCurrency = process.env.PORTFOLIO_BASE_CURRENCY ?? "USD";

  for (const account of accounts) {
    if (!account.id) continue;
    const payload = await snapTradeGet(
      `/accounts/${encodeURIComponent(account.id)}/positions/all`,
      clientId,
      consumerKey
    );
    const positions = Array.isArray(payload)
      ? payload
      : Array.isArray((payload as { results?: unknown }).results)
        ? ((payload as { results: SnapTradePosition[] }).results)
        : [];

    for (const position of positions as SnapTradePosition[]) {
      if (position.cash_equivalent === true) continue;
      const instrument = position.instrument;
      if (!instrument) continue;
      const kind = instrument?.kind?.trim().toLowerCase();
      const symbol = instrument?.symbol?.trim().toUpperCase();
      if (!kind || !symbol || !supportedKinds.has(kind)) continue;
      const positionCurrency = currency(position.currency ?? instrument.currency);
      if (positionCurrency && positionCurrency !== baseCurrency.toUpperCase()) continue;
      const units = Number(position.units ?? 0);
      if (Number.isFinite(units) && units > 0) {
        quantities.set(symbol, (quantities.get(symbol) ?? 0) + units);
      }
    }
  }

  return Array.from(quantities.entries())
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([symbol, quantity]) => ({ symbol, quantity }));
}

async function snapTradeGet(resource: string, clientId: string, consumerKey: string) {
  const timestamp = Math.floor(Date.now() / 1000);
  const query = new URLSearchParams({ clientId, timestamp: String(timestamp) }).toString();
  const signature = signSnapTradeRequest(`/api/v1${resource}`, query, consumerKey);
  const response = await fetch(`${baseUrl}${resource}?${query}`, {
    headers: {
      Accept: "application/json",
      Signature: signature
    },
    cache: "no-store"
  });
  if (!response.ok) {
    return Promise.reject(new Error(`SnapTrade read failed with status ${response.status}`));
  }
  return response.json();
}

function signSnapTradeRequest(pathname: string, query: string, consumerKey: string) {
  const canonical = JSON.stringify({ content: null, path: pathname, query });
  return crypto.createHmac("sha256", consumerKey).update(canonical).digest("base64");
}

async function readLocalConfig(): Promise<PortfolioConfig> {
  const file = path.join(process.cwd(), "portfolio.config.json");
  const text = await readFile(file, "utf8");
  return JSON.parse(text) as PortfolioConfig;
}

function currency(value: unknown) {
  if (typeof value === "object" && value && "code" in value) {
    return String(value.code ?? "").trim().toUpperCase();
  }
  return String(value ?? "").trim().toUpperCase();
}

function defaultSimilarPortfolios(): Array<{ name: string; holdings: Holding[] }> {
  return [
    {
      name: "US quality benchmark",
      holdings: [
        { symbol: "QUAL", quantity: 0.45 },
        { symbol: "SPY", quantity: 0.35 },
        { symbol: "MOAT", quantity: 0.2 }
      ]
    },
    {
      name: "Global equity blend",
      holdings: [
        { symbol: "SPY", quantity: 0.5 },
        { symbol: "EFA", quantity: 0.25 },
        { symbol: "EEM", quantity: 0.15 },
        { symbol: "QQQ", quantity: 0.1 }
      ]
    }
  ];
}

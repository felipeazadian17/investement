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
  price?: number | string;
  average_purchase_price?: number | string;
  averagePurchasePrice?: number | string;
  cost_basis?: number | string;
  costBasis?: number | string;
  book_value?: number | string;
  bookValue?: number | string;
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
  const holdings = new Map<string, Holding>();
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
        const existing = holdings.get(symbol);
        const costBasis = readCostBasis(position, units);
        const quantity = (existing?.quantity ?? 0) + units;
        holdings.set(symbol, {
          symbol,
          quantity,
          costBasis: weightedAverage(existing?.costBasis, existing?.quantity ?? 0, costBasis, units),
          assetType: assetTypeFor(kind),
          style: styleFor(symbol, kind),
          benchmark: benchmarkFor(symbol, kind)
        });
      }
    }
  }

  return Array.from(holdings.values()).sort((left, right) => left.symbol.localeCompare(right.symbol));
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

function readCostBasis(position: SnapTradePosition, units: number) {
  const perShare = firstNumber(
    position.average_purchase_price,
    position.averagePurchasePrice,
    position.costBasis,
    position.cost_basis
  );
  if (perShare !== null) return perShare;
  const totalCost = firstNumber(position.book_value, position.bookValue);
  if (totalCost !== null && units > 0) return totalCost / units;
  return undefined;
}

function firstNumber(...values: Array<number | string | undefined>) {
  for (const value of values) {
    const parsed = Number(value);
    if (Number.isFinite(parsed) && parsed > 0) return parsed;
  }
  return null;
}

function weightedAverage(
  existingCost: number | undefined,
  existingQuantity: number,
  nextCost: number | undefined,
  nextQuantity: number
) {
  if (existingCost === undefined) return nextCost;
  if (nextCost === undefined) return existingCost;
  const totalQuantity = existingQuantity + nextQuantity;
  return totalQuantity ? (existingCost * existingQuantity + nextCost * nextQuantity) / totalQuantity : undefined;
}

function assetTypeFor(kind: string): Holding["assetType"] {
  if (kind === "etf" || kind === "cef") return "etf";
  if (kind === "mutualfund") return "mutual_fund";
  if (kind === "crypto") return "crypto";
  if (kind === "stock" || kind === "adr") return "stock";
  return "other";
}

function styleFor(symbol: string, kind: string): Holding["style"] {
  if (kind !== "stock" && kind !== "adr") {
    if (symbol === "EEM" || symbol === "EFA") return "foreign";
    return "blend";
  }
  if (new Set(["MELI", "NVDA", "GLOB", "EXE"]).has(symbol)) return "growth";
  if (new Set(["AFL", "FE", "WTW"]).has(symbol)) return "dividend";
  if (new Set(["CTSH", "INCY", "PYPL", "REGN", "ERIE"]).has(symbol)) return "value";
  return "blend";
}

function benchmarkFor(symbol: string, kind: string) {
  const style = styleFor(symbol, kind);
  if (symbol === "EEM") return "EEM";
  if (symbol === "EFA") return "EFA";
  if (style === "foreign") return "EFA";
  if (style === "growth") return "QQQ";
  if (style === "value" || style === "dividend") return "QUAL";
  return "SPY";
}

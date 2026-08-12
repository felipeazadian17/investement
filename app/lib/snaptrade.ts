import crypto from "node:crypto";
import { readFile } from "node:fs/promises";
import path from "node:path";
import type { Holding, PortfolioActivity, PortfolioConfig } from "./types";

const legacyBaseUrl = "https://api.snaptrade.com/api/v1";
const supportedKinds = new Set(["adr", "cef", "crypto", "etf", "mutualfund", "stock"]);

type SnapTradeAccount = {
  id?: string;
  name?: string;
  institution_name?: string;
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
    description?: string | null;
    currency?: string | { code?: string };
  };
};

type SnapTradeBalance = {
  cash?: number | string | null;
  currency?: string | { code?: string };
};

type PositionPayload = {
  results?: SnapTradePosition[];
  data_freshness?: { as_of?: string };
};

type SnapTradeActivity = {
  id?: string;
  type?: string;
  description?: string;
  trade_date?: string | null;
  price?: number | string | null;
  units?: number | string | null;
  amount?: number | string | null;
  symbol?: {
    symbol?: string;
    raw_symbol?: string;
  };
};

export function hasSnapTradeCredentials() {
  return Boolean(
    process.env.SNAPTRADE_CLIENT_ID?.trim() && process.env.SNAPTRADE_CONSUMER_KEY?.trim()
  );
}

export async function loadPortfolioConfig(): Promise<PortfolioConfig> {
  const clientId = process.env.SNAPTRADE_CLIENT_ID?.trim();
  const consumerKey = process.env.SNAPTRADE_CONSUMER_KEY?.trim();

  if (clientId && consumerKey) {
    const portfolio = await readSnapTradePortfolio(clientId, consumerKey);
    return {
      baseCurrency: process.env.PORTFOLIO_BASE_CURRENCY ?? "USD",
      benchmark: process.env.PORTFOLIO_BENCHMARK ?? "SPY",
      ...portfolio,
      source: "snaptrade",
      similarPortfolios: defaultSimilarPortfolios()
    };
  }

  const file = path.join(process.cwd(), "portfolio.config.json");
  const text = await readFile(file, "utf8");
  return { ...(JSON.parse(text) as PortfolioConfig), source: "local" };
}

export async function readPortfolioActivities(startDate: string, endDate: string) {
  const clientId = process.env.SNAPTRADE_CLIENT_ID?.trim();
  const consumerKey = process.env.SNAPTRADE_CONSUMER_KEY?.trim();
  if (!clientId || !consumerKey) return [];

  const accounts = (await snapTradeGet("/accounts", clientId, consumerKey)) as SnapTradeAccount[];
  const accountActivities = await Promise.all(
    accounts
      .filter((account) => account.id)
      .map(async (account) => {
        const payload = await snapTradeGet(
          `/accounts/${encodeURIComponent(account.id as string)}/activities`,
          clientId,
          consumerKey,
          { startDate, endDate, type: "BUY,SELL", limit: "1000" }
        );
        return Array.isArray(payload)
          ? payload
          : Array.isArray((payload as { data?: unknown }).data)
            ? ((payload as { data: SnapTradeActivity[] }).data)
            : [];
      })
  );

  return accountActivities
    .flat()
    .map(normalizeActivity)
    .filter((activity): activity is PortfolioActivity => activity !== null)
    .sort((left, right) => right.tradeDate.localeCompare(left.tradeDate));
}

async function readSnapTradePortfolio(clientId: string, consumerKey: string) {
  const accounts = (await snapTradeGet("/accounts", clientId, consumerKey)) as SnapTradeAccount[];
  const holdings = new Map<string, Holding>();
  const baseCurrency = process.env.PORTFOLIO_BASE_CURRENCY ?? "USD";
  let cash = 0;
  let brokerAsOf: string | undefined;

  for (const account of accounts) {
    if (!account.id) continue;
    const [payload, balancesPayload] = await Promise.all([
      snapTradeGet(`/accounts/${encodeURIComponent(account.id)}/positions/all`, clientId, consumerKey),
      snapTradeGet(`/accounts/${encodeURIComponent(account.id)}/balances`, clientId, consumerKey)
    ]);
    const positionPayload = payload as PositionPayload;
    const positions = Array.isArray(payload)
      ? payload
      : Array.isArray(positionPayload.results)
        ? positionPayload.results
        : [];
    brokerAsOf = newestTimestamp(brokerAsOf, positionPayload.data_freshness?.as_of);
    const balances = Array.isArray(balancesPayload) ? (balancesPayload as SnapTradeBalance[]) : [];
    for (const balance of balances) {
      if (currency(balance.currency) !== baseCurrency.toUpperCase()) continue;
      const amount = Number(balance.cash ?? 0);
      if (Number.isFinite(amount)) cash += amount;
    }

    for (const position of positions as SnapTradePosition[]) {
      if (position.cash_equivalent === true) continue;
      const instrument = position.instrument;
      if (!instrument) continue;
      const kind = instrument.kind?.trim().toLowerCase();
      const symbol = instrument.symbol?.trim().toUpperCase();
      if (!kind || !symbol || !supportedKinds.has(kind)) continue;
      const positionCurrency = currency(position.currency ?? instrument.currency);
      if (positionCurrency && positionCurrency !== baseCurrency.toUpperCase()) continue;
      const units = Number(position.units ?? 0);
      if (!Number.isFinite(units) || units <= 0) continue;
      const existing = holdings.get(symbol);
      const costBasis = readCostBasis(position, units);
      const quantity = (existing?.quantity ?? 0) + units;
      holdings.set(symbol, {
        symbol,
        name: instrument.description?.trim() || existing?.name || symbol,
        quantity,
        costBasis: weightedAverage(existing?.costBasis, existing?.quantity ?? 0, costBasis, units),
        assetType: assetTypeFor(kind),
        style: styleFor(symbol, kind),
        benchmark: benchmarkFor(symbol, kind)
      });
    }
  }

  const accountNames = accounts.map((account) => account.name?.trim()).filter(Boolean) as string[];
  const institutions = Array.from(
    new Set(accounts.map((account) => account.institution_name?.trim()).filter(Boolean) as string[])
  );
  return {
    holdings: Array.from(holdings.values()).sort((left, right) => left.symbol.localeCompare(right.symbol)),
    cash,
    brokerAsOf,
    account: {
      name: accountNames.length === 1 ? accountNames[0] : "Portafolio consolidado",
      institution: institutions.join(" + ") || "Broker conectado",
      count: accounts.filter((account) => account.id).length
    }
  };
}

async function snapTradeGet(
  resource: string,
  clientId: string,
  consumerKey: string,
  params: Record<string, string> = {}
) {
  const timestamp = Math.floor(Date.now() / 1000);
  const query = new URLSearchParams({ clientId, timestamp: String(timestamp), ...params }).toString();
  const signature = signSnapTradeRequest(`/api/v1${resource}`, query, consumerKey);
  const response = await fetch(`${legacyBaseUrl}${resource}?${query}`, {
    headers: { Accept: "application/json", Signature: signature },
    cache: "no-store"
  });
  if (!response.ok) throw new Error(`SnapTrade read failed with status ${response.status}`);
  return response.json();
}

function signSnapTradeRequest(pathname: string, query: string, consumerKey: string) {
  const canonical = JSON.stringify({ content: null, path: pathname, query });
  return crypto.createHmac("sha256", consumerKey).update(canonical).digest("base64");
}

function normalizeActivity(activity: SnapTradeActivity): PortfolioActivity | null {
  const type = activity.type?.trim().toUpperCase();
  const tradeDate = activity.trade_date?.trim();
  if ((type !== "BUY" && type !== "SELL") || !tradeDate) return null;
  const symbol =
    activity.symbol?.raw_symbol?.trim().toUpperCase() ||
    activity.symbol?.symbol?.trim().toUpperCase() ||
    "-";
  return {
    id: activity.id ?? `${type}-${symbol}-${tradeDate}`,
    type,
    symbol,
    description: activity.description?.trim() || `${type} ${symbol}`,
    tradeDate,
    units: Math.abs(finiteNumber(activity.units)),
    price: Math.abs(finiteNumber(activity.price)),
    amount: Math.abs(finiteNumber(activity.amount))
  };
}

function finiteNumber(value: number | string | null | undefined) {
  const parsed = Number(value ?? 0);
  return Number.isFinite(parsed) ? parsed : 0;
}

function currency(value: unknown) {
  if (typeof value === "object" && value && "code" in value) {
    return String(value.code ?? "").trim().toUpperCase();
  }
  return String(value ?? "").trim().toUpperCase();
}

function newestTimestamp(current?: string, next?: string) {
  if (!next) return current;
  if (!current) return next;
  return new Date(next).getTime() > new Date(current).getTime() ? next : current;
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
  return totalCost !== null && units > 0 ? totalCost / units : undefined;
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
  if (new Set(["MELI", "GLOB", "WTW"]).has(symbol)) return "foreign";
  if (new Set(["NVDA", "EXE"]).has(symbol)) return "growth";
  if (new Set(["AFL", "FE"]).has(symbol)) return "dividend";
  if (new Set(["CTSH", "INCY", "PYPL", "REGN", "ERIE"]).has(symbol)) return "value";
  return "blend";
}

function benchmarkFor(symbol: string, kind: string) {
  if (kind === "etf" || kind === "cef") return symbol;
  if (symbol === "MELI" || symbol === "GLOB") return "EEM";
  if (symbol === "WTW") return "EFA";
  return "SPY";
}

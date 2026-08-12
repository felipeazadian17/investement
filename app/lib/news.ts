import { createHash } from "node:crypto";
import { XMLParser } from "fast-xml-parser";
import type { Holding, NewsArticle, NewsKind, NewsResponse, PortfolioEvent } from "./types";

const GOOGLE_NEWS_RSS = "https://news.google.com/rss/search";
const NASDAQ_CALENDAR = "https://api.nasdaq.com/api/calendar";
const parser = new XMLParser({ ignoreAttributes: false, trimValues: true });

type FeedItem = {
  title?: string;
  link?: string;
  pubDate?: string;
  source?: string | { "#text"?: string };
};

export async function fetchNewsDigest(holdings: Holding[]): Promise<NewsResponse> {
  const active = uniqueHoldings(holdings).slice(0, 40);
  const warnings: string[] = [];
  const companyResults = await Promise.allSettled(
    active.map(async (holding) => ({
      symbol: holding.symbol,
      articles: await fetchGoogleNews(companyQuery(holding), [holding.symbol], 4)
    }))
  );

  const portfolio = companyResults.map((result, index) => {
    if (result.status === "fulfilled") return result.value;
    warnings.push(`No se pudieron actualizar las noticias de ${active[index].symbol}.`);
    return { symbol: active[index].symbol, articles: [] };
  });

  const [marketResult, eventsResult] = await Promise.allSettled([
    fetchGoogleNews(
      '("financial markets" OR stocks OR bonds OR "Federal Reserve" OR "interest rates" OR inflation OR tariffs OR oil OR geopolitics OR war) (market OR economy OR investors OR finance) when:7d',
      [],
      24
    ),
    fetchUpcomingEvents(active.map((holding) => holding.symbol), 9)
  ]);

  if (marketResult.status === "rejected") warnings.push("No se pudieron actualizar las noticias de mercado.");
  if (eventsResult.status === "rejected") warnings.push("No se pudo actualizar el calendario de eventos.");

  return {
    asOf: new Date().toISOString(),
    portfolio,
    market: marketResult.status === "fulfilled" ? marketResult.value.filter(isMarketRelevant).slice(0, 12) : [],
    upcoming: eventsResult.status === "fulfilled" ? eventsResult.value : [],
    ...(warnings.length ? { warnings } : {})
  };
}

async function fetchGoogleNews(query: string, symbols: string[], limit: number) {
  const url = new URL(GOOGLE_NEWS_RSS);
  url.searchParams.set("q", query);
  url.searchParams.set("hl", "en-US");
  url.searchParams.set("gl", "US");
  url.searchParams.set("ceid", "US:en");

  const response = await fetch(url, {
    headers: { "User-Agent": "Investement Portfolio Dashboard/1.0" },
    next: { revalidate: 3600 },
    signal: AbortSignal.timeout(9_000)
  });
  if (!response.ok) throw new Error(`Google News respondió ${response.status}.`);

  const parsed = parser.parse(await response.text());
  const rawItems = parsed?.rss?.channel?.item;
  const items: FeedItem[] = Array.isArray(rawItems) ? rawItems : rawItems ? [rawItems] : [];
  const seen = new Set<string>();

  return items.reduce<NewsArticle[]>((articles, item) => {
    if (articles.length >= limit || !item.title || !item.link) return articles;
    const cleanTitle = item.title.replace(/\s+-\s+[^-]+$/, "").trim();
    if (symbols.length && isLowValueCompanyTitle(cleanTitle)) return articles;
    const key = cleanTitle.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
    if (!key || seen.has(key)) return articles;
    seen.add(key);
    articles.push({
      id: stableId(`${cleanTitle}|${item.link}`),
      title: cleanTitle,
      url: item.link,
      source: sourceName(item.source, item.title),
      publishedAt: validDate(item.pubDate),
      kind: classifyNews(cleanTitle),
      symbols
    });
    return articles;
  }, []);
}

async function fetchUpcomingEvents(symbols: string[], calendarDays: number) {
  const symbolSet = new Set(symbols.map((symbol) => symbol.toUpperCase()));
  const dates = Array.from({ length: calendarDays }, (_, index) => addDays(new Date(), index + 1));
  const results = await Promise.allSettled(
    dates.flatMap((date) => [fetchNasdaqEarnings(date), fetchNasdaqDividends(date)])
  );
  const events = results.flatMap((result) => (result.status === "fulfilled" ? result.value : []));
  return deduplicateEvents(events.filter((event) => symbolSet.has(event.symbol))).sort((a, b) =>
    a.date.localeCompare(b.date)
  );
}

async function fetchNasdaqEarnings(date: string): Promise<PortfolioEvent[]> {
  const payload = await fetchNasdaq("earnings", date);
  const rows = payload?.data?.rows;
  if (!Array.isArray(rows)) return [];
  return rows.flatMap((row: Record<string, unknown>) => {
    const symbol = textValue(row.symbol).toUpperCase();
    if (!symbol) return [];
    const timing = nasdaqTiming(textValue(row.time));
    const forecast = textValue(row.epsForecast);
    const quarter = textValue(row.fiscalQuarterEnding);
    return [{
      id: stableId(`earnings|${date}|${symbol}`),
      symbol,
      type: "earnings" as const,
      date,
      title: `${symbol} presenta resultados`,
      detail: [timing, quarter ? `trimestre ${quarter}` : "", forecast ? `EPS esperado ${forecast}` : ""]
        .filter(Boolean)
        .join(" · "),
      url: `https://www.nasdaq.com/market-activity/earnings?date=${date}`
    }];
  });
}

async function fetchNasdaqDividends(date: string): Promise<PortfolioEvent[]> {
  const payload = await fetchNasdaq("dividends", date);
  const rows = payload?.data?.calendar?.rows ?? payload?.data?.rows;
  if (!Array.isArray(rows)) return [];
  return rows.flatMap((row: Record<string, unknown>) => {
    const symbol = textValue(row.symbol).toUpperCase();
    if (!symbol) return [];
    const exDate = normalizeNasdaqDate(textValue(row.dividend_Ex_Date), date);
    const rate = textValue(row.dividend_Rate);
    const payment = humanNasdaqDate(textValue(row.payment_Date));
    return [{
      id: stableId(`dividend|${exDate}|${symbol}`),
      symbol,
      type: "dividend" as const,
      date: exDate,
      title: `${symbol} cotiza ex-dividendo`,
      detail: [rate ? `dividendo ${rate}` : "", payment ? `pago ${payment}` : ""].filter(Boolean).join(" · "),
      url: "https://www.nasdaq.com/market-activity/dividends"
    }];
  });
}

async function fetchNasdaq(kind: "earnings" | "dividends", date: string) {
  const url = `${NASDAQ_CALENDAR}/${kind}?date=${date}`;
  const response = await fetch(url, {
    headers: {
      Accept: "application/json, text/plain, */*",
      "Accept-Language": "en-US,en;q=0.9",
      "User-Agent": "Mozilla/5.0 (compatible; InvestementDashboard/1.0)"
    },
    next: { revalidate: 21_600 },
    signal: AbortSignal.timeout(8_000)
  });
  if (!response.ok) throw new Error(`Nasdaq respondió ${response.status}.`);
  return response.json();
}

function uniqueHoldings(holdings: Holding[]) {
  const seen = new Set<string>();
  return holdings.filter((holding) => {
    const symbol = holding.symbol.toUpperCase();
    if (!symbol || seen.has(symbol)) return false;
    seen.add(symbol);
    return true;
  });
}

function companyQuery(holding: Holding) {
  const name = holding.name?.replace(/\b(Inc\.?|Corp\.?|Corporation|Ltd\.?|PLC|Common Stock)\b/gi, "").trim();
  const identity = name && name.toUpperCase() !== holding.symbol.toUpperCase()
    ? `("${name}" OR "${holding.symbol}")`
    : `"${holding.symbol}"`;
  return `${identity} (stock OR shares OR earnings OR dividend OR guidance) when:30d`;
}

function classifyNews(title: string): NewsKind {
  const value = title.toLowerCase();
  if (/dividend|ex-date|distribution|yield/.test(value)) return "dividend";
  if (/earnings|results|revenue|profit|quarter|eps\b/.test(value)) return "earnings";
  if (/guidance|outlook|forecast/.test(value)) return "guidance";
  if (/analyst|upgrade|downgrade|rating|price target/.test(value)) return "analyst";
  if (/acquisition|merger|buyout|takeover|deal\b/.test(value)) return "deal";
  if (/regulat|lawsuit|antitrust|sec\b|fda\b|probe|investigation/.test(value)) return "regulation";
  if (/war\b|conflict|sanction|geopolit|tariff/.test(value)) return "geopolitics";
  if (/federal reserve|central bank|interest rate|inflation|jobs report|gdp\b/.test(value)) return "macro";
  if (/market|stocks|bonds|treasur|oil|dollar/.test(value)) return "markets";
  return "company";
}

function isLowValueCompanyTitle(title: string) {
  return /\b(call|put) option\b|stock price, news, quote|stock chart\b|revenue breakdown|holding history/i.test(title);
}

function isMarketRelevant(article: NewsArticle) {
  if (/car loan|personal loan|credit card|savings account|funding selections/i.test(article.title)) return false;
  if (article.kind !== "company") return true;
  return /market|stock|bond|treasur|rate|inflation|econom|investor|oil|war|tariff|sanction/i.test(article.title);
}

function nasdaqTiming(value: string) {
  const labels: Record<string, string> = {
    "time-before-hours": "antes de la apertura",
    "time-after-hours": "después del cierre",
    "time-not-supplied": "horario no confirmado"
  };
  return labels[value] || value || "horario no confirmado";
}

function humanNasdaqDate(value: string) {
  if (!value) return "";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat("es-UY", { day: "numeric", month: "short", timeZone: "UTC" }).format(parsed);
}

function sourceName(source: FeedItem["source"], title: string) {
  if (typeof source === "string") return source;
  if (source?.["#text"]) return source["#text"];
  return title.match(/\s+-\s+([^-]+)$/)?.[1]?.trim() ?? "Google News";
}

function validDate(value?: string) {
  const parsed = value ? new Date(value) : new Date();
  return Number.isNaN(parsed.getTime()) ? new Date().toISOString() : parsed.toISOString();
}

function addDays(date: Date, amount: number) {
  const next = new Date(date);
  next.setUTCDate(next.getUTCDate() + amount);
  return next.toISOString().slice(0, 10);
}

function normalizeNasdaqDate(value: string, fallback: string) {
  if (!value) return fallback;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? fallback : parsed.toISOString().slice(0, 10);
}

function deduplicateEvents(events: PortfolioEvent[]) {
  return Array.from(new Map(events.map((event) => [event.id, event])).values());
}

function textValue(value: unknown) {
  return typeof value === "string" || typeof value === "number" ? String(value).trim() : "";
}

function stableId(value: string) {
  return createHash("sha1").update(value).digest("hex").slice(0, 16);
}

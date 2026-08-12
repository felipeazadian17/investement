export type Holding = {
  symbol: string;
  name?: string;
  quantity: number;
  costBasis?: number;
  assetType?: "stock" | "etf" | "mutual_fund" | "crypto" | "other";
  style?: "value" | "growth" | "dividend" | "foreign" | "blend";
  benchmark?: string;
};

export type SimilarPortfolio = {
  name: string;
  holdings: Holding[];
};

export type PortfolioConfig = {
  baseCurrency: string;
  benchmark: string;
  cash?: number;
  account?: {
    name: string;
    institution: string;
    count: number;
  };
  source?: "snaptrade" | "local";
  brokerAsOf?: string;
  holdings: Holding[];
  similarPortfolios: SimilarPortfolio[];
};

export type PricePoint = {
  date: string;
  close: number;
};

export type MarketSeries = {
  symbol: string;
  price: number;
  previousClose: number;
  changePercent: number;
  history: PricePoint[];
};

export type MarketResponse = {
  asOf: string;
  series: MarketSeries[];
};

export type NewsKind =
  | "earnings"
  | "dividend"
  | "guidance"
  | "analyst"
  | "deal"
  | "regulation"
  | "macro"
  | "geopolitics"
  | "markets"
  | "company";

export type NewsArticle = {
  id: string;
  title: string;
  url: string;
  source: string;
  publishedAt: string;
  kind: NewsKind;
  symbols: string[];
};

export type NewsGroup = {
  symbol: string;
  articles: NewsArticle[];
};

export type PortfolioEvent = {
  id: string;
  symbol: string;
  type: "earnings" | "dividend";
  date: string;
  title: string;
  detail: string;
  url: string;
};

export type NewsResponse = {
  asOf: string;
  portfolio: NewsGroup[];
  market: NewsArticle[];
  upcoming: PortfolioEvent[];
  warnings?: string[];
};

export type PortfolioActivity = {
  id: string;
  type: "BUY" | "SELL";
  symbol: string;
  description: string;
  tradeDate: string;
  units: number;
  price: number;
  amount: number;
};

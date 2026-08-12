export type Holding = {
  symbol: string;
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

import { NextResponse } from "next/server";
import { loadPortfolioConfig } from "../../lib/snaptrade";

export const dynamic = "force-dynamic";

export async function GET() {
  const portfolio = await loadPortfolioConfig();
  return NextResponse.json(portfolio, {
    headers: {
      "Cache-Control": portfolio.source === "snaptrade"
        ? "s-maxage=60, stale-while-revalidate=300"
        : "no-store"
    }
  });
}

import { NextResponse } from "next/server";
import { fetchNewsDigest } from "../../lib/news";
import { loadPortfolioConfig } from "../../lib/snaptrade";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const maxDuration = 60;

export async function GET() {
  try {
    const portfolio = await loadPortfolioConfig();
    const news = await fetchNewsDigest(portfolio.holdings);
    return NextResponse.json(news, {
      headers: { "Cache-Control": "s-maxage=1800, stale-while-revalidate=3600" }
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "No se pudieron cargar las noticias.";
    return NextResponse.json({ error: message }, { status: 502 });
  }
}

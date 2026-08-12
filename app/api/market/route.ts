import { NextResponse } from "next/server";
import { fetchYahooSeries } from "../../lib/market-data";

export const dynamic = "force-dynamic";

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

import { NextRequest, NextResponse } from "next/server";
import { sendWeeklyReport } from "../../../lib/weekly-report";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 60;

export async function GET(request: NextRequest) {
  const secret = process.env.CRON_SECRET;
  if (!secret || request.headers.get("authorization") !== `Bearer ${secret}`) {
    return NextResponse.json({ error: "No autorizado." }, { status: 401 });
  }

  try {
    const result = await sendWeeklyReport();
    return NextResponse.json({ ok: true, ...result });
  } catch (error) {
    const message = error instanceof Error ? error.message : "No se pudo enviar el informe semanal.";
    console.error("Weekly report failed:", message);
    return NextResponse.json({ ok: false, error: message }, { status: 500 });
  }
}

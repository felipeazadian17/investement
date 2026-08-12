import nodemailer from "nodemailer";
import { fetchYahooSeries } from "./market-data";
import { fetchNewsDigest } from "./news";
import { buildCompositeBenchmark, buildPortfolioView } from "./portfolio";
import { loadPortfolioConfig, readPortfolioActivities } from "./snaptrade";
import type { MarketSeries, NewsArticle, PortfolioActivity, PortfolioEvent } from "./types";

const timezone = process.env.WEEKLY_REPORT_TIMEZONE || "America/Montevideo";

export async function sendWeeklyReport() {
  const smtp = readSmtpConfig();
  const now = new Date();
  const start = addDays(now, -7);
  const portfolio = await loadPortfolioConfig();
  const marketSymbols = Array.from(new Set([
    portfolio.benchmark,
    ...portfolio.holdings.map((holding) => holding.symbol),
    ...portfolio.holdings.map((holding) => holding.benchmark).filter((symbol): symbol is string => Boolean(symbol))
  ]));

  const [marketResults, activitiesResult, newsResult] = await Promise.all([
    Promise.allSettled(marketSymbols.map((symbol) => fetchYahooSeries(symbol, "1mo"))),
    readPortfolioActivities(isoDate(start), isoDate(now))
      .then((activities) => ({ activities, unavailable: false }))
      .catch((error) => {
        console.error("Portfolio activities read failed:", error instanceof Error ? error.message : error);
        return { activities: [] as PortfolioActivity[], unavailable: true };
      }),
    fetchNewsDigest(portfolio.holdings)
  ]);
  const market = marketResults.flatMap((result) => (result.status === "fulfilled" ? [result.value] : []));
  if (!market.length) throw new Error("No hay cotizaciones disponibles para generar el informe semanal.");

  const benchmark = market.find((series) => series.symbol === portfolio.benchmark);
  const view = buildPortfolioView(portfolio.holdings, market, benchmark, portfolio.cash ?? 0);
  const benchmarkPerformance = buildCompositeBenchmark(portfolio.holdings, market);
  const portfolioWeek = periodReturn(view.performance);
  const benchmarkWeek = periodReturn(benchmarkPerformance);
  const movers = weeklyMovers(view.positions, market).slice(0, 5);
  const reportRange = `${formatDate(start)} al ${formatDate(now)}`;
  const subject = `Resumen semanal del portafolio | ${reportRange}`;
  const html = renderEmail({
    reportRange,
    totalValue: view.totalValue,
    portfolioWeek,
    benchmarkWeek,
    dailyChange: view.dayChange,
    dailyChangePercent: view.dayChangePercent,
    movers,
    activities: activitiesResult.activities,
    activitiesUnavailable: activitiesResult.unavailable,
    events: newsResult.upcoming,
    marketNews: newsResult.market.slice(0, 5)
  });

  const transport = nodemailer.createTransport({
    host: smtp.host,
    port: smtp.port,
    secure: smtp.secure,
    auth: { user: smtp.username, pass: smtp.password }
  });
  const result = await transport.sendMail({
    from: smtp.from,
    to: smtp.to,
    subject,
    html,
    text: renderText({
      reportRange,
      totalValue: view.totalValue,
      portfolioWeek,
      benchmarkWeek,
      activities: activitiesResult.activities,
      events: newsResult.upcoming
    }),
    messageId: `<portfolio-weekly-${isoDate(now)}@investement-report>`,
    headers: { "X-Entity-Ref-ID": `portfolio-weekly-${isoDate(now)}` }
  });

  return {
    messageId: result.messageId,
    recipients: smtp.to,
    range: reportRange,
    activities: activitiesResult.activities.length,
    upcomingEvents: newsResult.upcoming.length
  };
}

function readSmtpConfig() {
  const values = {
    host: process.env.SMTP_HOST?.trim(),
    username: process.env.SMTP_USERNAME?.trim(),
    password: process.env.SMTP_PASSWORD?.trim(),
    from: process.env.SMTP_FROM?.trim(),
    to: process.env.WEEKLY_REPORT_TO?.split(",").map((value) => value.trim()).filter(Boolean) ?? []
  };
  const missing = [
    ["SMTP_HOST", values.host],
    ["SMTP_USERNAME", values.username],
    ["SMTP_PASSWORD", values.password],
    ["SMTP_FROM", values.from],
    ["WEEKLY_REPORT_TO", values.to.length]
  ].filter(([, value]) => !value).map(([name]) => name);
  if (missing.length) throw new Error(`Faltan variables de correo: ${missing.join(", ")}.`);
  const port = Number(process.env.SMTP_PORT || 587);
  return {
    host: values.host as string,
    username: values.username as string,
    password: values.password as string,
    from: values.from as string,
    to: values.to,
    port: Number.isFinite(port) ? port : 587,
    secure: process.env.SMTP_SECURE === "true" || port === 465
  };
}

function weeklyMovers(
  positions: Array<{ symbol: string; name: string; quantity: number }>,
  market: MarketSeries[]
) {
  const bySymbol = new Map(market.map((series) => [series.symbol, series]));
  return positions.map((position) => {
    const history = bySymbol.get(position.symbol)?.history ?? [];
    const current = history.at(-1)?.close ?? 0;
    const previous = history.at(Math.max(0, history.length - 6))?.close ?? current;
    const change = (current - previous) * position.quantity;
    return {
      symbol: position.symbol,
      name: position.name,
      change,
      percent: previous ? (current / previous - 1) * 100 : 0
    };
  }).sort((left, right) => Math.abs(right.change) - Math.abs(left.change));
}

function periodReturn(points: Array<{ portfolio: number }>) {
  if (points.length < 2) return 0;
  const latest = points.at(-1)?.portfolio ?? 0;
  const earlier = points.at(Math.max(0, points.length - 6))?.portfolio ?? 0;
  return ((100 + latest) / (100 + earlier) - 1) * 100;
}

function renderEmail(input: {
  reportRange: string;
  totalValue: number;
  portfolioWeek: number;
  benchmarkWeek: number;
  dailyChange: number;
  dailyChangePercent: number;
  movers: Array<{ symbol: string; name: string; change: number; percent: number }>;
  activities: PortfolioActivity[];
  activitiesUnavailable: boolean;
  events: PortfolioEvent[];
  marketNews: NewsArticle[];
}) {
  const alpha = input.portfolioWeek - input.benchmarkWeek;
  return `<!doctype html>
<html lang="es"><body style="margin:0;background:#f4f6f5;color:#18201d;font-family:Arial,sans-serif">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr><td align="center" style="padding:28px 12px">
<table role="presentation" width="680" style="max-width:680px;width:100%;background:#fff;border:1px solid #d9dfdc;border-radius:8px;border-collapse:separate;overflow:hidden">
<tr><td style="padding:24px 28px;border-bottom:1px solid #e9edeb"><div style="font-size:12px;color:#77817d;text-transform:uppercase">Portfolio · Informe ejecutivo</div><h1 style="margin:6px 0 0;font-size:24px">Resumen semanal</h1><div style="margin-top:5px;color:#77817d;font-size:13px">${escapeHtml(input.reportRange)}</div></td></tr>
<tr><td style="padding:24px 28px"><h2 style="margin:0 0 14px;font-size:17px">Resumen</h2>
<table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr>
${metric("Valor total", money(input.totalValue))}${metric("Semana", signedPercent(input.portfolioWeek), color(input.portfolioWeek))}${metric("Benchmark", signedPercent(input.benchmarkWeek), color(input.benchmarkWeek))}${metric("Diferencial", signedPercent(alpha), color(alpha))}
</tr></table>
<p style="margin:18px 0 10px;font-size:13px;color:#3f4a46">El último cambio diario fue de <strong style="color:${color(input.dailyChange)}">${signedMoney(input.dailyChange)} (${signedPercent(input.dailyChangePercent)})</strong>.</p>
${input.movers.length ? `<table role="presentation" width="100%" cellspacing="0" cellpadding="7" style="border-top:1px solid #e9edeb">${input.movers.map((mover) => `<tr><td><strong>${escapeHtml(mover.symbol)}</strong><br><span style="color:#77817d;font-size:11px">${escapeHtml(mover.name)}</span></td><td align="right" style="color:${color(mover.change)}"><strong>${signedMoney(mover.change)}</strong><br><span style="font-size:11px">${signedPercent(mover.percent)}</span></td></tr>`).join("")}</table>` : ""}
</td></tr>
<tr><td style="padding:24px 28px;border-top:1px solid #e9edeb"><h2 style="margin:0 0 14px;font-size:17px">Cambios en el portafolio</h2>
${input.activities.length ? `<table role="presentation" width="100%" cellspacing="0" cellpadding="8" style="font-size:13px"><tr style="color:#77817d"><th align="left">Fecha</th><th align="left">Movimiento</th><th align="right">Cantidad</th><th align="right">Importe</th></tr>${input.activities.map(activityRow).join("")}</table>` : emptyMessage(input.activitiesUnavailable ? "No se pudo actualizar el registro de compras y ventas para este informe." : "No se registraron compras ni ventas durante la semana.")}
</td></tr>
<tr><td style="padding:24px 28px;border-top:1px solid #e9edeb"><h2 style="margin:0 0 14px;font-size:17px">Próxima semana</h2>
${input.events.length ? input.events.map(eventRow).join("") : emptyMessage("No hay earnings ni fechas ex-dividendo confirmadas para las posiciones actuales.")}
${input.marketNews.length ? `<h3 style="margin:22px 0 8px;font-size:13px;text-transform:uppercase;color:#77817d">Contexto de mercado</h3>${input.marketNews.map(newsRow).join("")}` : ""}
</td></tr>
<tr><td style="padding:17px 28px;border-top:1px solid #e9edeb;color:#77817d;font-size:11px">Datos estimados para seguimiento personal. Verificá fechas y cifras con la fuente oficial antes de tomar decisiones.</td></tr>
</table></td></tr></table></body></html>`;
}

function renderText(input: {
  reportRange: string;
  totalValue: number;
  portfolioWeek: number;
  benchmarkWeek: number;
  activities: PortfolioActivity[];
  events: PortfolioEvent[];
}) {
  const activities = input.activities.length
    ? input.activities.map((item) => `${item.tradeDate}: ${item.type} ${item.symbol}, ${item.units} unidades, ${money(item.amount)}`).join("\n")
    : "Sin compras ni ventas registradas.";
  const events = input.events.length
    ? input.events.map((item) => `${item.date}: ${item.title} (${item.detail})`).join("\n")
    : "Sin earnings ni fechas ex-dividendo confirmadas.";
  return `Resumen semanal | ${input.reportRange}\n\nValor total: ${money(input.totalValue)}\nSemana: ${signedPercent(input.portfolioWeek)}\nBenchmark: ${signedPercent(input.benchmarkWeek)}\n\nCAMBIOS EN EL PORTAFOLIO\n${activities}\n\nPRÓXIMA SEMANA\n${events}`;
}

function metric(label: string, value: string, valueColor = "#18201d") {
  return `<td valign="top" style="width:25%;padding:11px;border:1px solid #e9edeb"><div style="font-size:10px;text-transform:uppercase;color:#77817d">${label}</div><strong style="display:block;margin-top:5px;font-size:16px;color:${valueColor}">${value}</strong></td>`;
}

function activityRow(activity: PortfolioActivity) {
  const type = activity.type === "BUY" ? "Compra" : "Venta";
  return `<tr style="border-top:1px solid #e9edeb"><td>${escapeHtml(shortDate(activity.tradeDate))}</td><td><strong>${type} ${escapeHtml(activity.symbol)}</strong><br><span style="color:#77817d;font-size:11px">${escapeHtml(activity.description)}</span></td><td align="right">${number(activity.units)}</td><td align="right">${money(activity.amount)}</td></tr>`;
}

function eventRow(event: PortfolioEvent) {
  return `<div style="padding:10px 0;border-bottom:1px solid #e9edeb;font-size:13px"><strong>${escapeHtml(shortDate(event.date))} · ${escapeHtml(event.title)}</strong><div style="margin-top:3px;color:#77817d">${escapeHtml(event.detail)}</div></div>`;
}

function newsRow(article: NewsArticle) {
  return `<div style="padding:8px 0;border-bottom:1px solid #e9edeb;font-size:13px"><a href="${escapeHtml(article.url)}" style="color:#245f9f;text-decoration:none"><strong>${escapeHtml(article.title)}</strong></a><div style="margin-top:3px;color:#77817d;font-size:11px">${escapeHtml(article.source)} · ${shortDate(article.publishedAt)}</div></div>`;
}

function emptyMessage(message: string) {
  return `<div style="padding:13px;background:#f8faf9;border:1px solid #e9edeb;color:#77817d;font-size:13px">${message}</div>`;
}

function addDays(date: Date, amount: number) {
  const next = new Date(date);
  next.setDate(next.getDate() + amount);
  return next;
}

function isoDate(date: Date) {
  return new Intl.DateTimeFormat("en-CA", { timeZone: timezone }).format(date);
}

function formatDate(date: Date) {
  return new Intl.DateTimeFormat("es-UY", { day: "numeric", month: "short", year: "numeric", timeZone: timezone }).format(date);
}

function shortDate(value: string) {
  const date = new Date(value.length === 10 ? `${value}T12:00:00Z` : value);
  return new Intl.DateTimeFormat("es-UY", { day: "2-digit", month: "short", timeZone: timezone }).format(date);
}

function money(value: number) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 }).format(value);
}

function signedMoney(value: number) {
  return `${value >= 0 ? "+" : "-"}${money(Math.abs(value))}`;
}

function signedPercent(value: number) {
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function number(value: number) {
  return new Intl.NumberFormat("es-UY", { maximumFractionDigits: 4 }).format(value);
}

function color(value: number) {
  return value >= 0 ? "#136f63" : "#b94d46";
}

function escapeHtml(value: string) {
  return value.replace(/[&<>'"]/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;"
  })[character] as string);
}

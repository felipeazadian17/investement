# Skills descargadas para los puntos 1 a 6

Fecha de revision: 2026-07-29.

Estas skills se conservan como guias de trabajo auditables. No son dependencias
de runtime y su contenido no reemplaza validaciones, formulas ni controles en
codigo. Antes de descargarlas se revisaron el `SKILL.md`, el repositorio de
origen y la utilidad concreta para este proyecto.

## Seleccion

| Skill | Origen | Punto | Uso dentro del proyecto |
| --- | --- | --- | --- |
| `yfinance` | [HKUDS/Vibe-Trading](https://github.com/HKUDS/Vibe-Trading/tree/main/agent/src/skills/yfinance) | 1 | simbolos, limites, ajustes y batching de Yahoo |
| `edgar-sec-filings` | [HKUDS/Vibe-Trading](https://github.com/HKUDS/Vibe-Trading/tree/main/agent/src/skills/edgar-sec-filings) | 1 | XBRL as-filed, LTM causal, formularios y riesgos |
| `financial-statement` | [HKUDS/Vibe-Trading](https://github.com/HKUDS/Vibe-Trading/tree/main/agent/src/skills/financial-statement) | 1-2 | LTM, conciliacion, ROIC y calidad de earnings |
| `dcf` | [virattt/dexter](https://github.com/virattt/dexter/tree/main/src/skills/dcf) | 2 | FCFF/WACC, convergencia, puente y sensibilidad |
| `valuation-model` | [HKUDS/Vibe-Trading](https://github.com/HKUDS/Vibe-Trading/tree/main/agent/src/skills/valuation-model) | 2 | seleccion DCF/DDM/RI/SOTP y trampas de valuacion |
| `creating-financial-models` | [anthropics/claude-cookbooks](https://github.com/anthropics/claude-cookbooks/tree/main/skills/custom_skills/creating-financial-models) | 2 | modelos point-in-time, escenarios y validaciones |
| `asset-allocation` | [HKUDS/Vibe-Trading](https://github.com/HKUDS/Vibe-Trading/tree/main/agent/src/skills/asset-allocation) | 3 | restricciones, riesgo, turnover y fallbacks |
| `risk-management` | CFA y contrato local | 3-6 | hard limits, tail risk, stress y veto neutral |
| `investment-governance` | CFA, Prefect y Dagster | 3-6 | pesos del comite, disenso, versionado y evidencia independiente |
| `broker-read-only` | SnapTrade y OWASP | 5-6 | frontera Personal read-only, retries, secretos y reconciliacion |
| `backtest-diagnose` | [HKUDS/Vibe-Trading](https://github.com/HKUDS/Vibe-Trading/tree/main/agent/src/skills/backtest-diagnose) | 4 | hard gates y diagnostico de resultados anormales |
| `execution-model` | [HKUDS/Vibe-Trading](https://github.com/HKUDS/Vibe-Trading/tree/main/agent/src/skills/execution-model) | 4 | delay, comisiones, slippage e impacto |
| `technical-analysis` | CFA, literatura academica y repos cuantitativos auditados | 2-4 | parametros estables, timing causal y validacion walk-forward |
| `report-generate` | [HKUDS/Vibe-Trading](https://github.com/HKUDS/Vibe-Trading/tree/main/agent/src/skills/report-generate) | 5 | reportes con fecha de corte, riesgos y disclaimer |
| `security-best-practices` | [openai/skills](https://github.com/openai/skills) | 5-6 | defaults seguros y manejo de secretos |
| `security-threat-model` | [openai/skills](https://github.com/openai/skills) | 5-6 | activos, fronteras de confianza y mitigaciones |
| `jupyter-notebook` | [openai/skills](https://github.com/openai/skills) | 1-4 | experimentos reproducibles futuros |

Vibe-Trading y Dexter publican licencia MIT. Las skills oficiales de OpenAI
incluyen su archivo `LICENSE.txt`. El contenido de Anthropic conserva su
procedencia. Las cinco skills de datos/valuacion fueron adaptadas localmente el
29 de julio de 2026 para reflejar el modelo probado del proyecto; ya no son copias
literales del upstream.

## Decisiones tomadas a partir de las skills

- `yfinance` se usa con `auto_adjust=False` explicito y normalizacion propia.
- Toda observacion guarda `retrieved_at`, `available_at` y referencia de origen.
- EDGAR requiere identidad con email, usa el XBRL as-filed aceptado antes de
  `as_of`, distingue duration/instant facts y construye LTM con
  `FY + YTD actual - YTD comparable`.
- `CFO - capex` se etiqueta como cash flow levered bajo US GAAP. FCFF se
  reconcilia agregando interes after-tax o desde NOPAT y reinversion.
- WACC usa risk-free, ERP, beta, spread y pesos de mercado fechados. Las tablas
  sectoriales son contraste o fallback documentado, no inputs primarios.
- La proyeccion conserva extremos observados y controla extrapolacion mediante
  convergencia de growth, margen y ROIC.
- El terminal liga `g`, reinversion y ROIC estable; exige `g < WACC`,
  `g <= risk-free` y `g < stable ROIC`.
- El puente a common equity incorpora caja, inversiones, deuda, leases,
  preferred, NCI y pensiones sin duplicar net debt/cash.
- La valuacion relativa genera perfiles desde LTM XBRL, selecciona 5-12 peers
  por similitud economica con cobertura minima y conserva todos los rechazos.
  El multiplo nunca participa en la seleccion y los multiplos EV aplican el
  puente EV-to-equity antes de combinarse con valores por accion.
- La sensibilidad DCF es 5x5 y marca supuestos economicamente invalidos como
  `N/A`.
- Financieras se derivan a residual income/DDM. Startups y EBIT negativo exigen
  escenarios de supervivencia, margen, capital y dilucion.
- Los pesos de terceros pasan por restricciones propias; nunca se aceptan sin
  validar concentracion y capital invertido.
- Todo backtest aplica al menos un bar de delay y costos configurables.
- El agente tecnico usa un baseline diario fijo y separa el score de una senal
  tactica no vinculante; cualquier cambio requiere validacion walk-forward.
- Portfolio usa inverse volatility restringido como baseline, cash dinamico para
  el limite de volatilidad, tail risk, risk contributions y bandas de rebalanceo.
- Riesgo aprobado tiene score neutral; hard breaches conservan veto.
- El comite evita doble conteo DCF/comparables y registra pesos efectivos.
- SnapTrade, audit log y workflows aplican redaccion en profundidad, retries
  acotados, versionado y validacion anticipada de dependencias.
- El workflow registra inicios, resultados y fallas en un log encadenado.
- SnapTrade queda limitado por capacidades: la fachada solo ofrece consultas.

## Skills descartadas

- `finance-airoom`: mezcla afirmaciones promocionales, supuestos fijos y un
  backtest rigido de TQQQ; no ofrece una base metodologica confiable.
- Skills crypto-first de ejecucion: amplian innecesariamente la superficie de
  riesgo y no corresponden al alcance read-only de la primera version.
- Orquestadores atados a runtimes especificos: se prefirio un workflow local
  pequeno con contratos propios, inspirado en los repos de la investigacion.

## Actualizacion

No actualizar estas carpetas a ciegas. Antes de reemplazar una skill hay que
revisar el diff, la licencia, nuevas herramientas permitidas y cambios de
supuestos financieros o de seguridad.

Para cambios del agente fundamental, revisar en la misma tarea si deben
sincronizarse `dcf`, `valuation-model`, `creating-financial-models`,
`financial-statement` y `edgar-sec-filings`. El detalle metodologico vigente esta en
[`../investigacion/auditoria_modelo_dcf.md`](../investigacion/auditoria_modelo_dcf.md).
Para cambios del agente tecnico, revisar tambien `technical-analysis` y
[`../investigacion/auditoria_modelo_tecnico.md`](../investigacion/auditoria_modelo_tecnico.md).
Para portfolio, riesgo y comite, revisar `asset-allocation`, `risk-management`,
`investment-governance` y
[`../investigacion/auditoria_portfolio_riesgo_gobernanza.md`](../investigacion/auditoria_portfolio_riesgo_gobernanza.md).
Para broker, auditor o workflows, revisar `broker-read-only`,
`security-best-practices`, `execution-model` y
[`../investigacion/auditoria_agentes_operativos.md`](../investigacion/auditoria_agentes_operativos.md).

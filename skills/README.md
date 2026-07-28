# Skills descargadas para los puntos 1 a 6

Fecha de revision: 2026-07-28.

Estas skills se conservan como guias de trabajo auditables. No son dependencias
de runtime y su contenido no reemplaza validaciones, formulas ni controles en
codigo. Antes de descargarlas se revisaron el `SKILL.md`, el repositorio de
origen y la utilidad concreta para este proyecto.

## Seleccion

| Skill | Origen | Punto | Uso dentro del proyecto |
| --- | --- | --- | --- |
| `yfinance` | [HKUDS/Vibe-Trading](https://github.com/HKUDS/Vibe-Trading/tree/main/agent/src/skills/yfinance) | 1 | simbolos, limites, ajustes y batching de Yahoo |
| `edgar-sec-filings` | [HKUDS/Vibe-Trading](https://github.com/HKUDS/Vibe-Trading/tree/main/agent/src/skills/edgar-sec-filings) | 1 | formularios SEC, fechas y lectura de riesgos |
| `financial-statement` | [HKUDS/Vibe-Trading](https://github.com/HKUDS/Vibe-Trading/tree/main/agent/src/skills/financial-statement) | 1-2 | conciliacion de estados y banderas de calidad |
| `dcf` | [virattt/dexter](https://github.com/virattt/dexter/tree/main/src/skills/dcf) | 2 | workflow DCF, sensibilidad y sanity checks |
| `valuation-model` | [HKUDS/Vibe-Trading](https://github.com/HKUDS/Vibe-Trading/tree/main/agent/src/skills/valuation-model) | 2 | DCF, comparables y trampas de valuacion |
| `creating-financial-models` | [anthropics/claude-cookbooks](https://github.com/anthropics/claude-cookbooks/tree/main/skills/custom_skills/creating-financial-models) | 2 | separacion inputs/calculos/output y escenarios |
| `asset-allocation` | [HKUDS/Vibe-Trading](https://github.com/HKUDS/Vibe-Trading/tree/main/agent/src/skills/asset-allocation) | 3 | restricciones, riesgo, turnover y fallbacks |
| `backtest-diagnose` | [HKUDS/Vibe-Trading](https://github.com/HKUDS/Vibe-Trading/tree/main/agent/src/skills/backtest-diagnose) | 4 | hard gates y diagnostico de resultados anormales |
| `execution-model` | [HKUDS/Vibe-Trading](https://github.com/HKUDS/Vibe-Trading/tree/main/agent/src/skills/execution-model) | 4 | delay, comisiones, slippage e impacto |
| `report-generate` | [HKUDS/Vibe-Trading](https://github.com/HKUDS/Vibe-Trading/tree/main/agent/src/skills/report-generate) | 5 | reportes con fecha de corte, riesgos y disclaimer |
| `security-best-practices` | [openai/skills](https://github.com/openai/skills) | 5-6 | defaults seguros y manejo de secretos |
| `security-threat-model` | [openai/skills](https://github.com/openai/skills) | 5-6 | activos, fronteras de confianza y mitigaciones |
| `jupyter-notebook` | [openai/skills](https://github.com/openai/skills) | 1-4 | experimentos reproducibles futuros |

Vibe-Trading y Dexter publican licencia MIT. Las skills oficiales de OpenAI
incluyen su archivo `LICENSE.txt`. El contenido de Anthropic se conserva con su
procedencia; sus scripts de ejemplo no se importan desde el paquete local.

## Decisiones tomadas a partir de las skills

- `yfinance` se usa con `auto_adjust=False` explicito y normalizacion propia.
- Toda observacion guarda `retrieved_at`, `available_at` y referencia de origen.
- EDGAR requiere una identidad con email y excluye enmiendas por defecto para
  evitar duplicados en la primera version.
- El DCF rechaza `WACC <= g`, siempre admite sensibilidad y expone cuanto valor
  proviene del terminal.
- Los pesos de terceros pasan por restricciones propias; nunca se aceptan sin
  validar concentracion y capital invertido.
- Todo backtest aplica al menos un bar de delay y costos configurables.
- El workflow registra inicios, resultados y fallas en un log encadenado.
- Schwab queda limitado por capacidades: la fachada solo ofrece consultas.

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


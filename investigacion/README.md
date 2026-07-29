# Investigacion de proyectos y componentes reutilizables

Fecha de la investigacion: 2026-07-28.

Este documento registra los proyectos publicos analizados y las decisiones de
reutilizacion para construir Investement. Los conteos de estrellas son una
fotografia aproximada al momento de la investigacion y no reemplazan la revision
de mantenimiento, pruebas, seguridad o licencia.

## Criterios de seleccion

- Ajuste con los agentes definidos en el README principal.
- Separacion entre investigacion asistida por LLM y calculos deterministas.
- Licencia compatible con reutilizacion e integracion.
- Calidad de datos, trazabilidad y proteccion contra look-ahead bias.
- Capacidad de operar primero en recomendacion, simulacion y auditoria.
- Actividad, documentacion, pruebas y adopcion del repositorio.
- Facilidad para reemplazar proveedores de datos, modelos LLM y brokers.

## Metodologia y alcance

La busqueda combino repositorios de GitHub, paginas de releases y licencias,
metadatos de PyPI, documentacion oficial de proveedores y discusiones de
usuarios en Reddit. Se priorizaron proyectos con alta adopcion, pero las
estrellas no se usaron como sustituto de una auditoria: tambien se revisaron
actividad reciente, issues, arquitectura, dependencias, licencia y advertencias
de los propios mantenedores.

La fotografia de GitHub se tomo el 2026-07-28. Los conteos cambian y algunos
proyectos recientes muestran relaciones de estrellas y forks inusuales; por
eso la shortlist ordena relevancia tecnica y no popularidad bruta. Las skills
descargadas fueron leidas antes de usarlas y no se incorporo codigo de los
repositorios de referencia al nucleo.

## Shortlist principal

### TradingAgents

- Repositorio: https://github.com/TauricResearch/TradingAgents
- Licencia: Apache-2.0.
- Traccion observada: aproximadamente 94.8k estrellas.
- Stack principal: Python y LangGraph.
- Cobertura: analista fundamental, tecnico, noticias y sentimiento; debate bull
  versus bear; trader; equipo de riesgo; portfolio manager; memoria y
  checkpoints.
- Partes relevantes: grafo de estados, contratos entre agentes, debate
  estructurado, decision log, reanudacion desde checkpoints y separacion entre
  analisis y aprobacion final.
- Decision: usar como referencia principal de orquestacion, sin adoptar su
  supuesto de que cada corrida debe terminar en una operacion.
- Riesgo: los resultados varian con el modelo, datos en vivo y sampling. Su
  backtest no debe tomarse como evidencia de rendimiento reproducible.

### OpenBB

- Repositorio: https://github.com/OpenBB-finance/OpenBB
- Licencia: AGPLv3.
- Traccion observada: aproximadamente 68.2k estrellas.
- Stack principal: Python, FastAPI, extensiones de proveedores, REST y MCP.
- Cobertura: precios, fundamentales, economia, ETFs, opciones, renta fija,
  indices y multiples proveedores de datos.
- Partes relevantes: contratos estandarizados para proveedores, normalizacion,
  fallback y exposicion de datos a Python, REST y agentes.
- Decision: estudiar sus interfaces y, si se usa, mantenerlo como servicio
  externo claramente separado. No copiar codigo AGPL dentro del nucleo sin una
  decision explicita sobre licencia.
- Riesgo: la licencia AGPL puede imponer obligaciones sobre productos derivados
  o servicios en red. Tambien hereda limites y calidad de los proveedores.

### AI Hedge Fund

- Repositorio: https://github.com/virattt/ai-hedge-fund
- Licencia: MIT.
- Traccion observada: aproximadamente 62.4k estrellas.
- Stack principal: Python, Poetry y multiples proveedores LLM.
- Cobertura: agentes de estilos de inversion, valoracion, fundamentales,
  tecnicos, sentimiento, riesgo y portfolio manager.
- Partes relevantes: schemas de senales, composicion de analistas, CLI,
  backtester de demostracion y soporte de modelos locales.
- Decision: reutilizar ideas de contratos y pruebas, no las personalidades como
  fuente de verdad financiera.
- Riesgo: el propio proyecto se define como proof of concept y no ejecuta
  operaciones. Muchas decisiones dependen de prompts y no de modelos
  financieros verificables.

### daily_stock_analysis

- Repositorio: https://github.com/ZhuLinsen/daily_stock_analysis
- Licencia: MIT.
- Traccion observada: aproximadamente 59.2k estrellas.
- Stack principal: Python, FastAPI, workflows programados y Web UI.
- Cobertura: multiples mercados, fuentes con fallback, fundamentales, noticias,
  indicadores, reportes diarios, historico, backtest y notificaciones.
- Partes relevantes: ejecucion programada, manejo de fallos de proveedores,
  persistencia de reportes y modo dry-run.
- Decision: usar como referencia operativa para scheduling y reportes.
- Riesgo: esta orientado principalmente al ecosistema de datos asiatico y parte
  de su configuracion promociona proveedores especificos.

### Microsoft Qlib

- Repositorio: https://github.com/microsoft/qlib
- Licencia: MIT.
- Traccion observada: aproximadamente 46.7k estrellas.
- Stack principal: Python y pipelines declarativos.
- Cobertura: ingestion y procesamiento de datos, factores, modelos de machine
  learning, backtesting, evaluacion, optimizacion y ejecucion.
- Partes relevantes: separacion dataset/modelo/estrategia/ejecucion, workflows
  reproducibles, evaluacion con costos y analisis de senales.
- Decision: reservar para investigacion cuantitativa avanzada. No usar como
  dependencia central de la primera version.
- Riesgo: curva de aprendizaje y alcance mayores que el problema inicial; varios
  ejemplos y datasets estan centrados en China.

### Vibe-Trading

- Repositorio: https://github.com/HKUDS/Vibe-Trading
- Licencia general: MIT, con atribuciones y licencias adicionales por alpha zoo.
- Traccion observada: aproximadamente 28.1k estrellas.
- Stack principal: Python, LangGraph, React, REST y MCP.
- Cobertura: investigacion en lenguaje natural, memoria, hipotesis, backtesting,
  datos point-in-time, run cards, equipos multiagente y broker channels.
- Partes relevantes: hypothesis registry, validaciones anti-look-ahead,
  aislamiento de codigo generado, memoria persistente, auditoria de corridas y
  alpha zoo.
- Decision: usar como segunda referencia para auditoria, backtesting y memoria.
- Riesgo: superficie funcional muy grande y ejecucion experimental. Cada grupo
  de factores requiere revisar atribucion y licencia por separado.

### Dexter

- Repositorio: https://github.com/virattt/dexter
- Licencia: MIT.
- Traccion observada: aproximadamente 27.5k estrellas.
- Stack principal: TypeScript, Bun y LangChain.
- Cobertura: planificacion de investigacion, herramientas financieras, busqueda,
  auto-validacion, limites de pasos, deteccion de loops y evaluaciones.
- Partes relevantes: planner, tool registry, scratchpad acotado, self-validation
  y harness de evaluacion financiera.
- Decision: trasladar patrones, no codigo directo, porque el nucleo de
  Investement sera Python.
- Riesgo: depende de Financial Datasets y buscadores externos para parte de su
  valor; LLM-as-judge no reemplaza respuestas deterministas.

### FinRobot

- Repositorio: https://github.com/AI4Finance-Foundation/FinRobot
- Licencia: Apache-2.0.
- Traccion observada: aproximadamente 7.7k estrellas.
- Stack principal: Python, PydanticAI, FastAPI, SQLite y React/Tauri.
- Cobertura: equity research, DCF, DDM, LBO, WACC, comparables, Monte Carlo,
  debate bull/bear/judge, reportes y multiples proveedores.
- Partes relevantes: operadores financieros puros, provenance numerica,
  separacion estricta entre calculo y narracion, reportes con evidencia y
  proveedores con failover.
- Decision: referencia principal para Fundamental y Relative Valuation.
- Riesgo: el producto completo es demasiado grande para integrarlo como una
  sola dependencia; deben extraerse contratos y formulas de forma selectiva.

## Alternativas evaluadas y no integradas ahora

### FinGPT y FinRL

- Repositorios: https://github.com/AI4Finance-Foundation/FinGPT y
  https://github.com/AI4Finance-Foundation/FinRL
- Cobertura: modelos de lenguaje financieros, sentimiento, benchmarks y deep
  reinforcement learning para decisiones secuenciales.
- Decision: mantenerlos como candidatos para una fase experimental. La primera
  version necesita trazabilidad y calculos deterministas antes que fine-tuning
  o politicas DRL dificiles de explicar.
- Nota: FinRL conserva el framework educativo original y remite el trabajo de
  produccion nuevo a FinRL-X/FinRL-Trading.

### QuantConnect LEAN

- Repositorio: https://github.com/QuantConnect/Lean
- Licencia: Apache-2.0; aproximadamente 19.2k estrellas.
- Cobertura: motor event-driven profesional, backtesting, datos, optimizacion y
  live trading multi-mercado en C# con soporte Python.
- Decision: excelente candidato para validar estrategias y fills en una fase
  posterior. No se integra ahora porque introduce un runtime y modelo operativo
  mucho mayores que nuestro pipeline Python read-only.

### Backtrader, Zipline Reloaded y Freqtrade

- Repositorios: https://github.com/mementum/backtrader,
  https://github.com/stefan-jansen/zipline-reloaded y
  https://github.com/freqtrade/freqtrade
- Cobertura: motores event-driven y, en Freqtrade, automatizacion orientada a
  cripto y ejecucion.
- Decision: no integrarlos en el primer corte. Mantener un motor causal pequeno
  permite auditar timing y costos; vectorbt cubre exploracion rapida y LEAN es
  una futura comprobacion independiente mas completa.

## Evidencia de Reddit y documentacion general

Estas fuentes son evidencia cualitativa, no benchmarks. Se usaron para buscar
fallos repetidos y restricciones operativas que los README promocionales suelen
omitir.

- [LLMs para trading](https://www.reddit.com/r/algotrading/comments/1k1s8q9/llms_for_trading/)
  y [discusion de arquitectura de agentes](https://www.reddit.com/r/algotrading/comments/1srw7oz/what_do_you_think_about_this_agent_set_up/): la
  señal comunitaria mas consistente es usar LLMs para investigacion,
  sentimiento y sintesis, no para calculos ni entradas/salidas directas. Esto
  fundamenta nuestra frontera entre LLM y codigo determinista.
- [Bug de look-ahead en backtests generados por LLM](https://www.reddit.com/r/algotrading/comments/1tpren4/letting_an_llm_write_your_backtest_check_for_this/):
  recomienda revisar lag de señales, precio de ejecucion, costos, slippage,
  survivorship y disponibilidad temporal. Esos puntos forman parte de nuestros
  tests y del contrato causal del backtester.
- [Vectorizado versus event-driven](https://www.reddit.com/r/algotrading/comments/1q6vyxr/vectorized_vs_event_driven_backtesting/)
  y [workflow de backtesting](https://www.reddit.com/r/algotrading/comments/1rb2f2b/im_just_starting_in_quantitative_trading_is_my/):
  vectorizacion sirve para explorar rapido; un motor causal o event-driven
  ofrece mejor control de ejecucion. Por eso vectorbt es opcional y existe un
  fallback propio verificable.
- [Limites de yfinance en produccion](https://www.reddit.com/r/algotrading/comments/mh6t0l/ok_yfinance_is_not_good_enough_for_production_any/)
  y [rate limits durante backtests](https://www.reddit.com/r/algotrading/comments/1tte9ep/what_data_source_are_you_using_for_backtesting/):
  aparecen fallos, throttling y la recomendacion de cachear o contratar datos.
  Nuestra integracion agrega cache local y deja el proveedor reemplazable.
- [Documentacion y disclaimer de yfinance](https://ericpien.github.io/yfinance/index.html):
  confirma que no es una API oficial de Yahoo y que se orienta a investigacion
  y uso personal. No se lo considera fuente unica de produccion.
- [Fair Access de SEC EDGAR](https://www.sec.gov/filergroup/announcements-old/new-rate-control-limits)
  y [API oficial de datos SEC](https://data.sec.gov/): exigen una identidad de
  cliente reconocible y limitan automatizaciones a un maximo de 10 requests por
  segundo. El proveedor local exige nombre/email y delega throttling/cache a
  EdgarTools.
- [Documentacion de SnapTrade](https://docs.snaptrade.com/): la Personal API Key
  permite centralizar la lectura del broker sin incorporar un segundo flujo OAuth
  al proyecto. La fachada local no expone metodos de ordenes.
- [Licencia oficial de vectorbt](https://github.com/polakowo/vectorbt/blob/master/LICENSE.md):
  agrega Commons Clause a Apache-2.0 y restringe vender servicios cuyo valor
  derive sustancialmente del software. Se mantiene como extra opcional sujeto a
  revision legal.

## Componentes seleccionados para integracion

### Datos de mercado: yfinance

- Repositorio: https://github.com/ranaroussi/yfinance
- Paquete: `yfinance`.
- Licencia: Apache-2.0.
- Traccion observada: aproximadamente 23.9k estrellas.
- Uso previsto: precios diarios, historicos, metadatos basicos, ETFs y una fuente
  gratuita para desarrollo y pruebas.
- Integracion: detras de un `MarketDataProvider` propio y reemplazable.
- Limites: no es una API oficial de Yahoo; los datos son para investigacion y
  uso personal segun sus advertencias. No sera la unica fuente de produccion.

### SEC y fundamentales: EdgarTools

- Repositorio: https://github.com/dgunning/edgartools
- Paquete: `edgartools`.
- Licencia: MIT.
- Traccion observada: aproximadamente 2.5k estrellas.
- Uso previsto: 10-K, 10-Q, 8-K, XBRL, Form 4, 13F, 13D/G, estados financieros
  y texto preparado para analisis.
- Integracion: detras de un `FundamentalsProvider`, con cache y fecha de corte.
- Ventaja: objetos tipados, DataFrames, rate-limit awareness y acceso sin API
  key directamente a SEC EDGAR.
- Version revisada: 5.43.1; requiere Python 3.10 o superior.

### Contraste de mercado: Alpha Vantage

- Documentacion: https://www.alphavantage.co/documentation/
- Uso previsto: fuente secundaria independiente para contrastar cierres diarios
  de Yahoo y detectar diferencias superiores a una tolerancia explicita.
- Integracion: `AlphaVantageProvider` normaliza `TIME_SERIES_DAILY`; el wrapper
  `ReconciledMarketDataProvider` devuelve las barras primarias y adjunta el
  reporte de diferencias al snapshot.
- Limites: el endpoint diario es raw/as-traded y no incluye dividendos ni splits;
  por eso la comparacion se restringe por defecto a los ultimos 20 puntos. El
  plan gratuito entrega 100 observaciones con `compact`; `full` es premium.
- Secreto: `ALPHA_VANTAGE_API_KEY` vive en `.env.local` y nunca se versiona.

### Construccion de portfolio: PyPortfolioOpt

- Repositorio: https://github.com/PyPortfolio/PyPortfolioOpt
- Paquete: `PyPortfolioOpt`.
- Licencia: MIT.
- Traccion observada: aproximadamente 5.9k estrellas.
- Uso previsto: mean-variance, Black-Litterman, HRP, covariance shrinkage,
  objetivos y restricciones, y asignacion discreta.
- Integracion: adaptador propio que recibe retornos esperados, matriz de riesgo y
  restricciones derivadas del perfil del inversor.
- Version revisada: 1.6.0.

### Riesgo y optimizacion avanzada: Riskfolio-Lib

- Repositorio: https://github.com/dcajasn/Riskfolio-Lib
- Paquete: `riskfolio-lib`.
- Licencia: BSD-3-Clause.
- Traccion observada: aproximadamente 4.2k estrellas.
- Uso previsto: CVaR, drawdown, risk parity, downside risk, contribuciones al
  riesgo y optimizacion con restricciones avanzadas.
- Integracion: backend opcional del mismo contrato de construccion de portfolio.
- Limite: algunos problemas avanzados dependen de solvers pesados o comerciales.
- Version revisada: 7.3.0.

### Analitica de performance: QuantStats

- Repositorio: https://github.com/ranaroussi/quantstats
- Paquete: `quantstats`.
- Licencia: Apache-2.0.
- Uso previsto: Sharpe, Sortino, volatilidad, drawdown, rolling metrics, Monte
  Carlo y tear sheets HTML.
- Integracion: servicio de metricas que consume retornos ya calculados.
- Version revisada: 0.0.81; requiere Python 3.10 o superior.

### Backtesting exploratorio: vectorbt

- Repositorio: https://github.com/polakowo/vectorbt
- Paquete: `vectorbt`.
- Traccion observada: aproximadamente 8.5k estrellas.
- Uso previsto: backtests vectorizados, comparacion rapida de parametros y
  analisis de portfolios.
- Integracion: backend opcional detras de un contrato propio de backtesting.
- Version revisada: 1.1.0; requiere Python 3.11 o superior.
- Licencia: Apache-2.0 con Commons Clause. Permite uso interno, pero restringe
  vender un producto o servicio cuyo valor principal sea vectorbt. Debe pasar
  revision legal antes de cualquier distribucion comercial; por eso permanece
  como extra opcional y existe un motor determinista propio.

### Broker: SnapTrade Personal

- Documentacion: https://docs.snaptrade.com/
- Uso previsto: lectura normalizada de cuentas, saldos y posiciones vinculadas.
- Integracion: `ReadOnlySnapTradeClient` y `SnapTradeBrokerAgent`.
- Credenciales: `clientId` y `consumerKey` guardados en macOS Keychain.
- Limite deliberado: no se exponen metodos para crear, modificar o cancelar ordenes.

## Mapeo a los agentes de Investement

| Agente | Reutilizacion principal | Responsabilidad propia |
| --- | --- | --- |
| Investor Profile | schemas tipados | objetivos, restricciones y validacion |
| Data | yfinance, EdgarTools, patron OpenBB | normalizacion, cache, fechas y provenance |
| Fundamental | formulas y patron FinRobot | DCF, calidad, supuestos y scoring |
| Technical | indicadores deterministas | senales reproducibles y regimen |
| Relative Valuation | DCF y comparables | margen de seguridad y condiciones de tesis |
| Portfolio Construction | PyPortfolioOpt, Riskfolio | restricciones del inversor y rebalanceo |
| Risk | Riskfolio, QuantStats | hard limits, bloqueos y explicaciones |
| Broker | SnapTrade Personal | cuentas, saldos y posiciones read-only |
| Auditor | patrones TradingAgents/Vibe-Trading | event log, hashes, versiones y resultados |

## Frontera entre codigo y LLM

El LLM puede buscar, clasificar, resumir, debatir y redactar. No debe calcular
flujos descontados, pesos, riesgo, performance, cantidades ni ordenes.

```text
Fuentes externas
    -> snapshots normalizados y fechados
    -> calculos deterministas
    -> senales estructuradas con evidencia
    -> agentes de investigacion y debate
    -> optimizador de portfolio
    -> risk gate determinista
    -> recomendacion y auditoria
    -> simulacion
    -> confirmacion humana
    -> broker, solo en una fase posterior
```

## Riesgos que deben cubrir las pruebas

- Look-ahead bias y uso de noticias posteriores a la fecha analizada.
- Survivorship bias en universos historicos.
- Ajustes por splits y dividendos.
- Monedas, zonas horarias, calendarios y dias sin mercado.
- Datos faltantes, stale data y discrepancias entre proveedores.
- Costos, slippage, impuestos y liquidez ignorados por el backtest.
- Optimizers inestables o sobreajustados a retornos historicos.
- Salidas LLM no validas, no reproducibles o sin evidencia.
- Secrets expuestos en logs o transferidos a codigo generado.
- Cualquier intento de ejecucion sin confirmacion humana.

## Plan de implementacion seleccionado

1. Integrar yfinance y EdgarTools mediante proveedores propios, con modelos
   normalizados, cache y provenance.
2. Implementar calculos propios de DCF, comparables y margen de seguridad,
   inspirados en la separacion determinista de FinRobot.
3. Integrar PyPortfolioOpt y Riskfolio-Lib detras de un contrato comun para
   construccion de portfolio y riesgo.
4. Integrar QuantStats y un backend de vectorbt para metricas y backtesting,
   manteniendo un fallback determinista simple.
5. Crear orquestacion, memoria, debate y auditoria propios usando los patrones de
   TradingAgents, FinRobot, Dexter y Vibe-Trading.
6. Crear un adaptador de SnapTrade Personal estrictamente read-only, con secretos
   fuera del repositorio y sin habilitar ordenes.

## Regla de adopcion

Cada dependencia debe quedar detras de una interfaz propia. Esto permite cambiar
fuentes de datos, optimizadores, backtesters, LLMs o brokers sin cambiar los
modelos de dominio ni el registro historico de decisiones.

## Implementacion local resultante

Los seis puntos quedaron implementados como una primera base vertical:

| Punto | Modulos locales | Estado |
| --- | --- | --- |
| 1. Datos | `src/investement/data/` y `src/investement/domain.py` | proveedores yfinance/EDGAR, normalizacion, cache y provenance |
| 2. Valuacion | `src/investement/valuation/` | DCF, sensibilidad, comparables y margen de seguridad |
| 3. Portfolio | `src/investement/portfolio/` | contrato comun, restricciones y backends opcionales |
| 4. Backtest | `src/investement/backtesting/` | motor causal, costos, metricas y adaptadores |
| 5. Orquestacion | `src/investement/orchestration/` y `src/investement/agents/` | nueve agentes, pipeline, comite, memoria y audit log con hash chain |
| 6. Broker | `src/investement/brokers/snaptrade_personal.py` | Personal API Key y superficie estrictamente read-only |

Las skills revisadas y su procedencia estan documentadas en
[`skills/README.md`](../skills/README.md). Las dependencias externas son extras
opcionales de `pyproject.toml`; el nucleo determinista no necesita red.

# Investement

Investement es un sistema de agentes para asistir en la construccion, analisis y gestion de un portfolio de inversion personalizado.

El objetivo es desarrollar un asesor de inversion que pueda recomendar compras, ventas, desinversiones y rebalanceos en base a analisis fundamental, analisis tecnico, gestion de riesgo y optimizacion de portfolio. El portfolio del broker se consulta exclusivamente mediante SnapTrade Personal en modo read-only.

> Nota: este proyecto no debe comenzar como un agente que opera automaticamente. La primera version debe funcionar en modo analisis, recomendacion, simulacion y auditoria. La ejecucion real requiere controles adicionales, permisos explicitos y validacion operativa.

## Vision

La tesis central del proyecto es detectar oportunidades donde el precio de mercado se desvie del valor fundamental estimado. El sistema buscara comprar activos cuando coticen por debajo de su valor razonable con margen de seguridad, y reducir o vender posiciones cuando el precio este caro respecto a sus fundamentos o cuando el riesgo asumido deje de estar justificado.

El portfolio resultante debe ser diversificado y buscar el mayor rendimiento esperado posible para el nivel de riesgo aceptado por el inversor.

## Principios

- Priorizar preservacion de capital y control de riesgo antes que rendimiento bruto.
- Separar recomendacion, simulacion y ejecucion real.
- Registrar cada decision, dato usado, tesis y resultado posterior.
- Evitar concentraciones excesivas por activo, sector, pais, factor o moneda.
- Explicar cada recomendacion con supuestos claros.
- Usar ejecucion automatica solo cuando existan controles, limites y confirmacion humana.

## Arquitectura Inicial

El sistema se piensa como una arquitectura por capas compuesta por agentes especializados.

### Agente de Perfil del Inversor

Define el marco de inversion personal:

- Objetivos financieros.
- Horizonte temporal.
- Moneda base.
- Tolerancia al riesgo.
- Liquidez necesaria.
- Restricciones fiscales.
- Sectores o activos prohibidos.
- Concentracion maxima por posicion.
- Drawdown aceptable.

### Agente de Datos

Recolecta y normaliza informacion necesaria para el analisis:

- Precios historicos y actuales.
- Fundamentales de companias.
- Balances y estados financieros.
- Ratios de valuacion.
- Tasas de interes.
- Inflacion.
- Tipo de cambio.
- Noticias y eventos relevantes.
- Portfolio actual.

La cuenta del broker se consulta mediante SnapTrade Personal. Los datos de mercado
y fundamentales se obtienen de proveedores separados y reemplazables.

### Agente Fundamental

Estima valor razonable y calidad de negocio usando, entre otros:

- DCF simplificado.
- Multiplos comparables.
- Earnings yield.
- Crecimiento esperado.
- Margenes.
- ROIC.
- Free cash flow.
- Endeudamiento.
- Recompras.
- Moat y riesgo competitivo.

### Agente Tecnico

Apoya decisiones de timing y control de entrada/salida. No busca adivinar graficos, sino complementar la tesis fundamental con datos de mercado:

- Tendencia.
- Momentum.
- Medias moviles.
- Volatilidad.
- RSI.
- MACD.
- Soportes y resistencias.
- Volumen.
- Regimen de mercado.

### Agente de Valuacion Relativa

Compara precio de mercado contra valor fundamental estimado y produce senales de inversion:

- Comprar.
- Mantener.
- Reducir.
- Vender.

Cada senal debe incluir margen de seguridad, nivel de conviccion, riesgos principales y condiciones que invalidarian la tesis.

### Agente de Construccion de Portfolio

Convierte senales individuales en una asignacion diversificada y coherente con el perfil del inversor.

Debe controlar:

- Peso maximo por activo.
- Peso por sector.
- Peso por pais.
- Exposicion por factor.
- Beta.
- Volatilidad.
- Correlacion.
- Liquidez.
- Tamano de posicion.

Metodos candidatos:

- Mean-variance con restricciones.
- Black-Litterman.
- Risk parity.
- Heuristicas robustas y simples para la primera version.

### Agente de Riesgo

Bloquea o alerta operaciones peligrosas:

- Concentracion excesiva.
- Apalancamiento no deseado.
- Drawdown elevado.
- Baja liquidez.
- Earnings u otros eventos proximos.
- Exposicion cambiaria no deseada.
- Ordenes demasiado grandes.
- Posibles problemas fiscales, como wash-sale si aplica.

### Agente de Broker SnapTrade

Responsable de consultar mediante SnapTrade las cuentas y posiciones vinculadas.

Fases previstas:

1. Solo lectura de cuenta y posiciones.
2. Simulacion de ordenes.
3. Generacion de ordenes pendientes.
4. Confirmacion humana obligatoria.
5. Registro completo de cada recomendacion.

### Agente Auditor

Registra cada recomendacion y decision para evaluar si el sistema agrega valor en el tiempo:

- Datos usados.
- Tesis de inversion.
- Precio observado.
- Valor razonable estimado.
- Recomendacion.
- Orden sugerida o ejecutada.
- Resultado posterior.
- Explicacion y aprendizaje.

## Alcance de la Primera Version

La primera version debe evitar trading automatico y enfocarse en construir una base confiable.

Objetivos iniciales:

- Leer o cargar el portfolio actual.
- Definir perfil de riesgo del inversor.
- Analizar una lista inicial de ETFs y acciones.
- Generar recomendaciones justificadas.
- Construir un portfolio objetivo.
- Mostrar rebalanceos sugeridos.
- Correr backtests basicos.
- Registrar historicamente recomendaciones y resultados.

## Roadmap Inicial

1. Definir modelo de datos para inversor, activos, posiciones, senales y recomendaciones.
2. Implementar carga manual del portfolio actual.
3. Crear analisis inicial de ETFs y acciones seleccionadas.
4. Construir motor simple de scoring fundamental y tecnico.
5. Generar portfolio objetivo con restricciones basicas.
6. Crear reporte de recomendaciones y rebalanceo.
7. Agregar backtesting basico.
8. Integrar datos externos confiables.
9. Integrar SnapTrade Personal en modo lectura.
10. Disenar flujo seguro para simulacion y ejecucion futura.

## Seguridad y Responsabilidad

Este sistema debe tratarse como una herramienta de apoyo a la decision, no como asesor financiero autonomo. Las recomendaciones deben ser revisadas por una persona antes de ejecutar operaciones reales.

La ejecucion automatica de trades solo debe habilitarse cuando existan:

- Autenticacion segura.
- Gestion de secretos.
- Limites de posicion.
- Limites de perdida.
- Confirmacion humana.
- Logs completos.
- Pruebas en simulacion.
- Mecanismos de cancelacion y monitoreo.

## Implementacion Actual

La primera base ejecutable de los puntos 1 a 6 ya esta disponible:

| Componente | Implementacion |
| --- | --- |
| Datos | proveedores normalizados, cache JSON atomico y provenance |
| Valuacion | DCF, sensibilidad, comparables robustos y margen de seguridad |
| Portfolio | restricciones propias y backends PyPortfolioOpt/Riskfolio |
| Backtesting | motor causal con delay, costos, metricas, QuantStats y vectorbt |
| Agentes | workflow, comite con disenso/veto, memoria y auditoria con hash chain |
| Broker | SnapTrade Personal estrictamente read-only, sin metodos de ordenes |

## Agentes Implementados

Cada rol del diseño inicial tiene ahora una clase concreta en
`src/investement/agents/`:

| Agente | Clase | Salida principal |
| --- | --- | --- |
| Perfil del inversor | `InvestorProfileAgent` | perfil normalizado y restricciones |
| Datos | `DataAgent` | snapshot point-in-time con evidencia |
| Fundamental | `FundamentalAgent` | DCF, calidad y hallazgo estructurado |
| Tecnico | `TechnicalAgent` | tendencia, momentum, RSI, MACD y riesgo observado |
| Valuacion relativa | `RelativeValuationAgent` | fair value combinado y margen de seguridad |
| Construccion de portfolio | `PortfolioConstructionAgent` | pesos objetivo y rebalanceos |
| Riesgo | `RiskAgent` | hard limits, explicaciones y veto |
| Broker SnapTrade | `SnapTradeBrokerAgent` | cuentas y posiciones read-only |
| Auditor | `AuditorAgent` | memoria y log con hash chain y secretos redactados |

### Perfil Personalizado

`InvestorProfileAgent` separa capacidad financiera, voluntad de asumir perdidas
y necesidad de riesgo. El perfil efectivo adopta la dimension mas conservadora
y deriva reserva de emergencia, capital inicialmente invertible, limites de
concentracion y limites distintos para activos individuales y para el portfolio.

Los datos personales se cargan desde `profiles/*.local.json`, que Git ignora.
La politica tributaria se versiona con fecha y fuentes, pero exige revision
profesional antes de transformarse en una decision de inversion. La investigacion
vigente para residentes fiscales uruguayos esta en
[`investigacion/tributacion_uruguay_2026.md`](investigacion/tributacion_uruguay_2026.md).

`InvestmentAgentPipeline` conecta los agentes de analisis con el comite, aplica
el veto de riesgo, construye el portfolio y registra cada corrida. El pipeline
no contiene una ruta para crear, reemplazar o cancelar ordenes.

La investigacion y shortlist estan en
[`investigacion/README.md`](investigacion/README.md). Las skills descargadas,
su procedencia y las decisiones que aportaron estan en
[`skills/README.md`](skills/README.md).

## Inicio Rapido

El stack completo usa Python 3.11 o superior. En macOS:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e '.[data,portfolio,analytics,snaptrade,dev]'
MPLBACKEND=Agg MPLCONFIGDIR=/tmp/investement-mpl .venv/bin/python -m pytest -q
.venv/bin/ruff check src tests
```

El nucleo determinista no necesita los extras:

```bash
.venv/bin/python -m pip install -e .
.venv/bin/python examples/research_pipeline.py
.venv/bin/python examples/agent_pipeline.py
```

## Integraciones

- Yahoo: `YFinanceProvider` fija `auto_adjust=False`, solicita acciones
  corporativas y construye hacia adelante un indice de retorno total causal. El
  precio vigente sigue siendo `Close`; `Adj Close` se conserva solo como
  metadata de diagnostico y no participa del calculo.
- SEC: `EdgarProvider` exige una identidad con email y extrae revenue, EBIT,
  cash flow operativo, capex, caja, deuda y acciones diluidas desde el XBRL del
  `10-K` o `10-Q` aceptado antes de `as_of`. No mezcla Company Facts revisados
  posteriormente.
- Fondos y derivados: `YFinanceProvider` normaliza asset classes, sectores,
  top holdings y operaciones de ETFs/fondos mutuos, ademas de calls y puts por
  vencimiento. Estos endpoints son current-only y rechazan fechas historicas.
- Contraste de mercado: `AlphaVantageProvider` aporta OHLCV diario raw y
  `ReconciledMarketDataProvider` compara los ultimos cierres superpuestos contra
  Yahoo, dejando diferencias y tolerancia en el snapshot.
- Optimizacion: los pesos de PyPortfolioOpt y Riskfolio siempre pasan por las
  restricciones deterministas locales.
- Analitica: QuantStats y vectorbt son opcionales. vectorbt 1.1.0 usa
  Apache-2.0 con Commons Clause y requiere revision antes de uso comercial.
- SnapTrade: la Personal API Key se guarda en macOS Keychain y la fachada solo
  permite leer cuentas, saldos y posiciones.

### Configuracion del agente de datos

La identidad SEC local ya debe incluir nombre y email. Para usar el contraste de
Alpha Vantage, crea una clave gratuita y guardala solamente en `.env.local`:

```bash
SEC_IDENTITY="Nombre Apellido email@example.com"
ALPHA_VANTAGE_API_KEY="tu-clave"
```

El plan gratuito de Alpha Vantage admite `outputsize="compact"` (ultimos 100
datos); `full` requiere plan premium. La composicion recomendada es:

```python
import os
from pathlib import Path

from investement.agents import DataAgent
from investement.data import (
    AlphaVantageProvider,
    EdgarProvider,
    ReconciledMarketDataProvider,
    YFinanceProvider,
)

yahoo = YFinanceProvider()
alpha = AlphaVantageProvider(os.environ["ALPHA_VANTAGE_API_KEY"])
edgar = EdgarProvider(
    identity=os.environ["SEC_IDENTITY"],
    data_directory=Path(".cache/edgar"),
    cache_directory=Path(".cache/edgar"),
)
data_agent = DataAgent(
    ReconciledMarketDataProvider(yahoo, alpha, relative_tolerance=0.01),
    filings=edgar,
    fundamentals=edgar,
    instruments=yahoo,
)
```

En `AssetDataRequest`, `include_fund_data=True` incorpora datos de ETF/fondo y
`option_expiration=date(...)` solicita una cadena concreta. Para backtests ambos
deben quedar desactivados salvo que exista un archivo historico fechado; los
fundamentales XBRL y las barras siguen respetando `as_of`.

### Conexion mediante SnapTrade Personal

El agente lee la cuenta vinculada mediante una Personal API Key de SnapTrade.
Este es el unico canal de conexion con el broker. Utiliza solamente `clientId` y
`consumerKey`; no crea usuarios SnapTrade internos y no expone metodos para operar.

```bash
.venv/bin/python -m investement.cli.snaptrade_connect
```

En macOS, el comando solicita ambas credenciales con entrada oculta y las guarda
en el Keychain bajo `investement.snaptrade.*`. La salida de verificacion omite
numeros e identificadores de cuenta. Para automatizacion tambien admite
`SNAPTRADE_CLIENT_ID` y `SNAPTRADE_CONSUMER_KEY` con `--non-interactive`.

`SnapTradeBrokerAgent.current_portfolio("USD")` convierte las cuentas vinculadas
en valor total, efectivo, valores por simbolo y pesos actuales. El pipeline puede
leer ese estado con `construct_portfolio_from_broker(...)`: evalua el riesgo del
portfolio existente, pero calcula la asignacion inicial desde pesos cero. Las
tenencias actuales no condicionan los pesos objetivo. La integracion sigue siendo
estrictamente de solo lectura.

El universo para la asignacion inicial no se limita a las posiciones actuales ni
a acciones del S&P 500. Debe considerar los instrumentos disponibles en Charles
Schwab, incluyendo acciones, ETFs, fondos mutuos y vehiculos de renta fija. Las
opciones pueden evaluarse como overlay excepcional, pero requieren valuacion por
contrato, multiplicadores, vencimiento y limites de exposicion antes de ingresar
al optimizador; no se aproximan como si fueran una accion ordinaria.

Por seguridad, la normalizacion falla ante monedas distintas de la moneda base,
posiciones cortas y derivados que requieran multiplicadores o valuacion propia.
Los fondos marcados por SnapTrade como equivalentes de efectivo no se cuentan dos
veces. Los precios dependen de la ultima sincronizacion disponible en SnapTrade.
Para verificar manualmente exactamente ese estado normalizado:

```bash
.venv/bin/python -m investement.cli.snaptrade_connect --non-interactive \
  --show-portfolio-state --base-currency USD
```

## Estado Actual

Base v0.1 implementada y probada con datos sinteticos. Yahoo fue validado con
precios, holdings de SPY y una cadena real de opciones; SEC XBRL fue validado con
un `10-Q` real de AAPL y fecha de corte. Alpha Vantage requiere una clave propia:
la clave publica `demo` ya no habilita la serie de prueba.

# Auditoria del modelo DCF

Fecha de revision: 2026-07-29.

## Criterio de modelado

El modelo productivo usa FCFF, no `CFO - capex` sin ajustar. La identidad es:

```text
FCFF = CFO + interes * (1 - tasa marginal) - capex
EV = PV(FCFF explicito) + PV(valor terminal)
Equity value = EV + activos no operativos - claims no comunes
```

Esto mantiene consistente el cash flow disponible para todos los proveedores de
capital con un WACC que tambien remunera a deuda y equity. CFA distingue FCFF,
descontado a WACC, de FCFE, descontado al costo de equity. Ademas indica que los
activos operativos y no operativos deben valuarse por separado y combinarse al
final: [CFA Free Cash Flow Valuation](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/free-cash-flow-valuation).

## Datos y LTM

- La fuente fundamental es el XBRL presentado en cada 10-K/10-Q y aceptado antes
  de `as_of`; no se usan inputs DCF escritos por el usuario.
- Se solicitan ocho filings por defecto. Un LTM trimestral aplica
  `FY + YTD actual - YTD comparable` a revenue, EBIT, CFO, capex, impuestos,
  intereses, D&A, SBC y net income.
- Las acciones diluidas LTM se reconstruyen con share-days. Balance, deuda, caja,
  inversiones, leases y otros claims salen del ultimo periodo.
- Cada valor conserva accession, concepto XBRL, fecha de aceptacion y fuente.

SEC explica la estructura y uso de los datos XBRL presentados en EDGAR en su
[guia oficial](https://www.sec.gov/files/edgar/xbrl-guide.pdf). El modelo no usa
Company Facts revisados posteriormente para reconstruir un pasado que el mercado
todavia no conocia.

## Proyeccion y convergencia

La solucion al problema de convergencia es un modelo driver-based de siete anos:

1. El crecimiento inicial es YTD contra YTD comparable, o FY contra FY. No se
   recorta por ser alto.
2. Revenue growth, margen EBIT y ROIC convergen linealmente a valores estables.
3. `NOPAT = revenue * margen EBIT * (1 - tax)`.
4. `reinvestment rate = growth / ROIC`.
5. `FCFF = NOPAT * (1 - reinvestment rate)`.

Por lo tanto, una empresa con crecimiento mayor a ROIC puede mostrar FCFF
negativo por reinversion sin que el codigo altere el dato. En terminal, ROIC
converge al WACC y `g` queda ligado a reinversion. Damodaran desarrolla esta
relacion y la necesidad de convergencia competitiva en
[Terminal value and excess returns](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/valquestions/termvalueexreturns.htm)
y [Growth and reinvestment](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/valquestions/growth.htm).

El forecast sigue el enfoque CFA de ligar revenue, costos, working capital,
capital investment y capital structure, y de usar escenarios cuando el riesgo
lo exige: [CFA Company Analysis: Forecasting](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/company-analysis-forecasting).

## WACC de mercado

El WACC se reconstruye automaticamente:

- Risk-free y ERP: observacion fechada de Damodaran. Al 1 de julio de 2026,
  risk-free USD 4.45% e implied ERP 4.18%:
  [Damodaran current data](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/home.htm).
- Beta: regresion de retornos mensuales de cinco anos contra SPY, minimo 24
  observaciones, con ajuste de convergencia `0.67 * raw beta + 0.33`.
- Costo de equity: CAPM con risk-free, beta ajustado y ERP.
- Costo de deuda: risk-free mas default spread segun interest coverage. Si el
  filing no separa intereses, el spread y la cobertura se resuelven de forma
  iterativa. La tabla y su fecha quedan registradas:
  [Damodaran synthetic ratings](https://pages.stern.nyu.edu/adamodar/New_Home_Page/datafile/ratings.html).
- Pesos: valores de mercado de equity y deuda mas leases, no pesos contables.
- Leases: al tratarlos como deuda, el interes implicito se reclasifica fuera de
  EBIT antes de calcular margen, NOPAT y ROIC. Asi no se resta el mismo claim dos
  veces.

El calculo coincide con el tratamiento de WACC y estructura de capital del
[CFA Capital Structure](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/capital-structure).
Ninguna observacion fechada posterior a `as_of` se acepta.

## Puente a equity

El puente suma caja, inversiones de corto plazo e inversiones de largo plazo, y
resta deuda, leases operativos, preferred stock, noncontrolling interests y
pasivos de pension. Usa el mayor entre acciones actuales y acciones diluidas LTM
cuando ambas existen. Cada componente queda visible; un dato ausente no se
presenta como precision confirmada y genera riesgo en el hallazgo.

## Terminal y sensibilidad

- `g` es nominal USD, no negativo, menor que WACC, menor o igual al risk-free y
  menor que el ROIC estable.
- La politica base usa el menor entre 2.5% y el risk-free observado.
- El FCFF terminal se calcula como
  `terminal NOPAT * (1 - g / stable ROIC)`.
- Cada corrida entrega una matriz 5x5: WACC en pasos de 1% y `g` en pasos de
  0.5%. Las celdas economicamente imposibles quedan en `None`, no explotan a un
  valor enorme.

La sensibilidad y los escenarios son herramientas expresas del
[CFA Financial Analysis Techniques](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/financial-analysis-techniques).

## Seleccion del modelo

El FCFF DCF se bloquea para:

- Bancos, aseguradoras y otras financieras identificadas por SIC 6000-6799.
  Deuda y reinversion son operativas en esas firmas. El siguiente modelo debe ser
  DDM o residual income.
- Empresas con EBIT negativo o invested capital no positivo. Para startups y
  companias en transicion corresponde un arbol de escenarios con supervivencia,
  revenue, margen y dilucion, no una perpetuidad puntual.

CFA senala residual income como alternativa cuando FCF es negativo:
[CFA Residual Income Valuation](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/residual-income-valuation).
Para instituciones financieras tambien se requiere analisis especializado:
[CFA Analysis of Financial Institutions](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/analysis-of-financial-institutions).

## Cobertura del temario CFA relevante

Se contrastaron Equity Valuation, Financial Statement Analysis, Corporate
Issuers, Quantitative Methods y Portfolio Management en los puntos que afectan
este DCF: seleccion de modelo, calidad del filing, normalizacion, forecasting,
WACC, beta, valor temporal, escenarios y sensibilidad. Fixed Income aporta la
logica de spread/costo de deuda. Derivatives, Ethics, Alternative Investments y
la construccion completa de portfolio no cambian la matematica de este DCF y se
mantienen en sus agentes correspondientes.

## Pendientes deliberados

- Implementar residual income/DDM para financieras.
- Agregar escenarios probabilisticos y dilucion explicita para startups.
- Incorporar working capital y capex con drivers de tres estados cuando exista
  suficiente historia XBRL; el modelo actual usa reinversion agregada via ROIC.
- Contrastar el costo de deuda sintetico con bonos/CDS del emisor cuando haya una
  fuente point-in-time licenciada.
- Migrar el backtest historico del S&P 500 a este pipeline. El proxy viejo de
  Yahoo con WACC fijo fue deshabilitado para impedir que produzca resultados
  aparentemente comparables con el modelo nuevo.

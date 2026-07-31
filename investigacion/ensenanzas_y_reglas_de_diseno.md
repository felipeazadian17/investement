# Ensenanzas y reglas de diseno

Fecha de consolidacion: 2026-07-30.

Este documento concentra las decisiones que deben sobrevivir a nuevas
implementaciones, cambios de proveedor y futuras corridas. No es un reporte de
una fecha particular ni debe depender de archivos generados en `resultados/`.

## 1. Perfil y riesgo

- El objetivo es crecimiento de capital a largo plazo, con revisiones
  semanales o mensuales y sin trading diario.
- La cartera es long-only por defecto. Short selling y leverage solo pueden
  habilitarse como excepcion explicita, con aprobacion humana y limite de riesgo.
- La tolerancia de drawdown del perfil pasa de 20% a **35% como guardrail
  blando**. La pandemia y otros shocks muestran que una cartera de renta
  variable puede atravesar caidas superiores a 20% sin que la tesis de largo
  plazo quede automaticamente invalidada.
- Esto no elimina los vetos duros: liquidez insuficiente, apalancamiento,
  concentracion, fraude, quiebra, evento corporativo material o incumplimiento
  de una restriccion contractual siguen bloqueando.
- La volatilidad anual objetivo de la cartera se mantiene en 18%. Drawdown y
  volatilidad miden riesgos distintos y no deben sustituirse entre si.
- El fondo de emergencia de seis meses esta fuera del portfolio, en una cuenta
  separada. Con gastos mensuales de USD 1.500, la reserva objetivo es USD 9.000
  y se considera cubierta. Los USD 80.000 quedan disponibles para invertir.
- El perfil personal usa `min_cash_weight=0`. Una reserva operativa temporal
  puede aparecer por ejecucion o rebalanceo, pero no es una asignacion objetivo.

## 2. Numero de instrumentos

No existe un numero universalmente optimo de tickers. La evidencia academica
encuentra beneficios decrecientes y resultados dependientes de correlaciones,
ponderaciones, mercado y periodo. Statman cuestiono que diez acciones agoten la
diversificacion; trabajos posteriores ubican una cartera de 30-40 acciones como
una referencia frecuente, mientras revisiones mas recientes concluyen que no
existe un numero magico.

La regla practica para este portfolio es:

- **18-24 instrumentos nominales** para que la cartera siga siendo auditable y
  manejable con revision mensual.
- **25-40 emisores efectivos** despues de reconstruir los holdings de los ETFs.
- Aproximadamente 4-6 ETFs amplios o factoriales y 10-14 acciones individuales.
- Ninguna accion individual por encima de 10%; objetivo normal de 3-6% para una
  accion satelite.
- Caps adicionales por emisor, sector, pais y factor. Un ETF no debe permitir
  esquivar un cap de emisor: su peso debe multiplicarse por el holding real.
- Medir numero efectivo de posiciones, contribuciones al riesgo y concentracion
  de los cinco mayores emisores. El conteo bruto de tickers es insuficiente.

La cartera revisada de 18 instrumentos cumple el primer punto, pero aun no
puede certificarse contra el segundo hasta integrar look-through de holdings.

## 3. Cartera revisada y lecciones de las simulaciones

La version revisada de la simulacion invirtio 95% y conservo 5% de cash como
escenario de investigacion. La politica productiva corregida invierte 100% del
capital disponible. Reduce la asignacion explicita a dividendos a 10% e incorpora
30% directo en NVDA, MSFT, META, GOOGL, AMZN y AAPL. QQQ, VTI y QUAL agregan
exposicion indirecta a varias de esas mismas companias.

En la ventana 2016-07-01 a 2026-07-29, con ejecucion `t+1` y costos de 5 bps:

| Estrategia | Retorno anual | Volatilidad | Sharpe | Max drawdown |
| --- | ---: | ---: | ---: | ---: |
| Cartera estrategica, 18 instrumentos | 19.86% | 17.92% | 1.11 | -30.02% |
| Equal weight | 19.37% | 16.96% | 1.14 | -29.70% |
| SPY con 5% cash, benchmark de la simulacion archivada | 14.66% | 17.37% | 0.84 | -32.71% |

Ensenanzas:

1. Ampliar de 12 a 18 instrumentos mejoro la cartera revisada, pero el cambio
   de composicion impide atribuir la mejora solamente al numero de tickers.
2. Equal weight tuvo mejor Sharpe y menor volatilidad en esta muestra; la
   politica estrategica tuvo mayor retorno y valor terminal. No hay evidencia
   suficiente para llamarla universalmente optima.
3. No rebalancear produjo mas retorno historico, pero tambien mucha mas
   concentracion, volatilidad y drawdown. No es la politica recomendada.
4. El torneo adaptativo logro 18.38% anualizado con turnover muy superior y no
   supero a la politica fija. Se conserva como benchmark, no como piloto
   automatico.
5. Los resultados son historicos, sensibles a la composicion del universo,
   survivorship bias, valuaciones iniciales, costos, impuestos y al periodo
   dominado por mega-cap estadounidenses. No son una promesa de alpha.

## 4. Modelos y datos

- Comparar siempre contra `1/N`, inverse volatility, politica fija y no
  rebalancear.
- Toda seleccion mensual debe usar ventana de estimacion, ventana de validacion
  previa y ejecucion posterior; nunca elegir por el retorno futuro.
- Black-Litterman y CVaR deben conservar sus etiquetas de proxy hasta incorporar
  vistas fundamentales point-in-time y un optimizador convexo completo.
- DCF, comparables, fundamentales y tecnico deben permanecer separados. El
  tecnico aporta timing de entrada o salida; no decide por si solo la tesis.
- Mantener fuente primaria, fuente secundaria de contraste, timestamp,
  calendario, moneda, precio de ejecucion y estado de cada dato.
- Usar `t+1` como baseline, aplicar costos, spread, slippage e impuestos cuando
  existan y dejar un log auditable de cada recomendacion.
- SnapTrade permanece read-only. Ningun script de investigacion puede enviar
  ordenes al broker.

## 5. Reglas antes de usar capital real

1. Mantener la reserva externa de USD 9.000 separada y no mezclarla con el
   capital de riesgo.
2. Implementar holdings look-through de ETFs y caps agregados por emisor,
   sector y factor.
3. Repetir el walk-forward con varios universos y periodos, sin survivorship
   bias, incluyendo mercados alcistas, bajistas, inflacionarios y crisis.
4. Comparar retornos netos de costos, impuestos uruguayos, retenciones,
   conversion UYU/USD y spreads reales.
5. Reconciliar diariamente posiciones y efectivo con SnapTrade durante una fase
   de paper portfolio.
6. Rebalancear mensualmente o por bandas; hacer un chequeo semanal solo por
   cambios materiales de tesis, riesgo o timing.
7. Registrar que una recomendacion puede ser correcta aunque el precio tarde en
   converger, y evaluar la tesis por horizonte, no por ruido diario.

## Fuentes de diversificacion

- [Statman, How Many Stocks Make a Diversified Portfolio?](https://www.cambridge.org/core/journals/journal-of-financial-and-quantitative-analysis/article/abs/how-many-stocks-make-a-diversified-portfolio/CE5CDF2C7225FC1E0EDE3E700A3C66A7)
- [Goetzmann y Kumar, Equity Portfolio Diversification](https://www.nber.org/papers/w8686)
- [Alexeev y Tapon, How Many Stocks Are Sufficient for Equity Portfolio Diversification? A Review of the Literature](https://www.mdpi.com/1911-8074/14/11/551)
- [On financial market correlation structures and diversification benefits](https://www.sciencedirect.com/science/article/pii/S0378437122004551)
- [CFA, Asset Allocation with Real-World Constraints](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/asset-allocation-with-real-world-constraints)

## Higiene del repositorio

- Los resultados fechados, CSV/JSON/HTML de corridas y backtests ad hoc quedan
  fuera del repositorio.
- Los tests unitarios y de integracion se conservan porque protegen el codigo
  productivo; no son artefactos de una corrida.
- Los modelos reutilizables de backtesting, restricciones y torneo permanecen
  en `src/`; los scripts de exploracion de una fecha concreta no.
- Las credenciales, perfiles personales y caches locales nunca deben entrar al
  control de versiones.

# Auditoria del modelo tecnico y senales de timing

Fecha de revision: 2026-07-29.

## Conclusion ejecutiva

No existe un conjunto universal de parametros tecnicos "optimos". El parametro
que maximiza un backtest dentro de muestra suele capturar ruido. Para este
proyecto se adopta un baseline estable, publicado y coherente con un inversor de
largo plazo. Cualquier cambio posterior debe sobrevivir validacion walk-forward,
costos, multiples subperiodos y multiples activos.

El analisis tecnico no decide si una empresa merece ser comprada. Describe el
regimen de precio y aporta una senal tactica de entrada, espera, reduccion o
salida al comite. La valuacion, el perfil, el portfolio y el riesgo conservan sus
propias decisiones y el riesgo mantiene poder de veto.

## Fuentes principales

- [CFA Institute, Market Efficiency, curriculum 2026](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/market-efficiency):
  la evidencia no permite asumir que reglas basadas en precios superaran
  consistentemente a mercados desarrollados; exige una explicacion economica y
  validacion fuera de muestra.
- [CFA Institute, Currency Management: An Introduction, 2026](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/currency-management-introduction):
  los indicadores tecnicos se usan para confirmar tendencias, soporte,
  resistencia y puntos de giro, no como una respuesta unica.
- [Moskowitz, Ooi y Pedersen, Time Series Momentum](https://w4.stern.nyu.edu/facdir/lpederse/papers/TimeSeriesMomentum.pdf):
  documenta persistencia de retornos de uno a doce meses y usa una senal de doce
  meses con holding mensual. El trabajo estudia futuros e indices, por lo que no
  se extrapola mecanicamente a cada accion.
- [Jegadeesh y Titman, Returns to Buying Winners and Selling Losers](https://doi.org/10.1111/j.1540-6261.1993.tb04702.x):
  documenta momentum cross-sectional en acciones a horizontes de tres a doce
  meses y reversion posterior.
- [Brock, Lakonishok y LeBaron, Simple Technical Trading Rules](https://doi.org/10.1111/j.1540-6261.1992.tb04681.x):
  estudia moving averages, breakouts y una banda de 1% para reducir whipsaw.
- [Sullivan, Timmermann y White, Data-Snooping, Technical Trading Rule Performance](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=160330):
  demuestra por que hay que corregir data snooping al comparar muchas reglas.
- [TA-Lib Python](https://github.com/TA-Lib/ta-lib-python), aproximadamente
  12 mil estrellas al revisar: referencia de implementacion para RSI 14,
  MACD 12/26/9 y ATR 14.
- [Backtrader](https://github.com/mementum/backtrader), aproximadamente 22.6
  mil estrellas: referencia event-driven, costos, slippage, ordenes y ejecucion.
- [Zipline](https://github.com/quantopian/zipline), aproximadamente 20 mil
  estrellas: referencia para evitar look-ahead y ejecutar decisiones en eventos
  posteriores al dato observado.
- [VectorBT](https://github.com/polakowo/vectorbt), aproximadamente 7.9 mil
  estrellas: parameter sweeps y robustness/walk-forward, usado para exploracion.
- [Alphalens](https://github.com/quantopian/alphalens), aproximadamente 4.3
  mil estrellas: IC, retornos por cuantiles, turnover y analisis por grupos.
- [Microsoft Qlib](https://github.com/microsoft/qlib): workflow de dataset,
  entrenamiento, backtest y evaluacion; reconoce non-stationarity y rolling
  retraining, y reporta resultados antes y despues de costos.

Las estrellas son una senal de adopcion, no evidencia de rentabilidad.

## Parametros baseline

Todos los periodos siguientes son barras diarias completas.

| Item | Parametro | Uso |
| --- | --- | --- |
| Historia | minimo 253; deseable 504 | SMA 200, momentum 12-1 y estabilidad |
| Tendencia | SMA 50 / SMA 200 | regimen intermedio/largo |
| Banda de tendencia | 1% | zona neutral para reducir whipsaw |
| Momentum largo | retorno de 252 a 21 dias | senal 12-1, evita reversion del ultimo mes |
| Momentum medio | 63 dias | confirmacion tactica trimestral |
| RSI | Wilder 14 | fuerza y recuperacion, condicionado al regimen |
| RSI alcista | soporte 40-50; extremo 80 | no vender solo por superar 70 |
| RSI bajista | resistencia 50-60; debilidad bajo 40 | no comprar solo por estar bajo 30 |
| MACD | EMA 12 / 26, signal 9 | cambio de momentum; usar histograma y pendiente |
| ATR normalizado | Wilder 14 | escala de movimiento y riesgo, no direccion |
| Volumen relativo | barra actual / media previa de 20 | confirmacion de breakout, no senal aislada |
| Breakout | maximo previo de 63 dias | disparador tactico dentro de regimen alcista |
| Volatilidad | 63 retornos, anualizacion 252 | riesgo reciente |
| Drawdown | ventana 252 | caida maxima y caida corriente desde el pico |
| Vigencia timing | 5 barras | obliga a recalcular antes de actuar |
| Ejecucion | primera barra posterior | evita operar con un cierre aun no conocido |

No se incluyen patrones de velas ni decenas de osciladores correlacionados. SMA,
momentum y MACD contienen informacion parcialmente redundante; sus pesos deben
impedir contar tres veces la misma tendencia.

## Logica de timing

### Entrada favorable

Requiere regimen alcista y al menos un disparador:

1. breakout sobre el maximo previo de 63 dias con volumen relativo mayor o igual
   a uno; o
2. recuperacion de pullback: RSI cruza al alza la zona 45 y el histograma MACD
   mejora; o
3. cruce confirmado de SMA 50 sobre SMA 200 atravesando la banda de 1%.

Momentum largo y medio negativos reducen o invalidan la fuerza. RSI sobre 80 no
es una venta automatica, pero evita perseguir una entrada extendida.

### Salida favorable

Requiere regimen bajista y confirmacion de al menos dos elementos: momentum largo
negativo, MACD bajo su signal, RSI bajo 40 o ruptura del minimo previo de 63 dias.
Esto reduce ventas por un unico indicador. Para una cartera long-only la salida
significa reducir o cerrar, nunca abrir un short.

### Estados intermedios

- `wait`: no hay setup de entrada o el activo esta extendido/debil.
- `hold`: tendencia favorable sin nuevo disparador.
- `tighten-risk`: deterioro parcial; revisar peso, tesis y stop operativo.

La senal no conoce por si sola si la cuenta ya tiene posicion. Por eso expresa
favorabilidad tactica y no una orden ejecutable.

## Score y confianza

Baseline del score direccional:

- tendencia 35%;
- momentum largo y medio 25%;
- MACD 15%;
- RSI condicionado al regimen 10%;
- volumen como confirmacion 5%;
- penalizacion por volatilidad, ATR y drawdown hasta 10%.

La confianza depende de historia disponible, completitud de volumen, acuerdo
entre familias y frescura. No debe crecer solo porque se agregaron barras. Una
senal tecnica mantendra menor autoridad que una evidencia fundamental de alta
calidad.

## Validacion obligatoria

1. Punto-in-time, acciones y universo historico sin survivorship bias.
2. Indicador calculado al cierre `t`; primera ejecucion posible en `t+1`.
3. Walk-forward con parametros fijados antes del test y embargo entre ventanas.
4. Comparacion contra buy-and-hold y contra no usar timing.
5. Costos, spread, slippage, impuestos aplicables y turnover.
6. Resultados por sector, capitalizacion, volatilidad y regimen de mercado.
7. IC/Spearman de score contra retornos forward de 5, 21 y 63 dias, hit rate,
   calibration, turnover, drawdown y estabilidad de coeficientes.
8. Sensibilidad alrededor del baseline, no busqueda del punto maximo.
9. Reality Check, deflated Sharpe u otra correccion si se prueban muchas reglas.
10. Paper trading antes de cualquier uso operativo.

No promover un cambio si solo mejora retorno total. Debe sostener calidad de
senal neta de costos, riesgo, estabilidad temporal y explicabilidad.

## Brechas de datos pendientes

- Benchmark SPY y benchmark sectorial point-in-time para relative strength.
- Calendario de mercado para expresar exactamente la proxima sesion ejecutable.
- Bid/ask y volumen intradia para estimar implementation shortfall.
- Historia sin survivorship bias para la evaluacion cross-sectional.

Estas brechas reducen confianza; no se rellenan con valores neutrales.

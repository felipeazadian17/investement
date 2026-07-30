# Auditoria de portfolio, riesgo y comite de inversion

Fecha de revision: 2026-07-29.

## Conclusion

No existe un optimizador ni una ventana universalmente optima. Para una cartera
personal long-only se adopta un baseline simple, restringido y auditable. La
complejidad solo se promueve si mejora resultados walk-forward netos de costos
frente a `1/N` e inverse volatility.

La asignacion estrategica, el control de riesgo y el timing son contratos
separados. El optimizador propone pesos; riesgo puede reducir exposicion o vetar;
el tecnico solo aporta timing; el comite no permite que ausencia de breaches se
interprete como alpha.

## Fuentes

- [CFA, Overview of Asset Allocation 2026](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/overview-asset-allocation):
  governance, risk budgeting, active risk y rebalanceo por calendario o bandas.
- [CFA, Asset Allocation with Real-World Constraints 2026](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/asset-allocation-with-real-world-constraints):
  liquidez bajo stress, horizonte, impuestos, restricciones y rangos de politica.
- [CFA, Measuring and Managing Market Risk 2026](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/measuring-managing-market-risk):
  VaR, contribucion marginal, sensibilidades, escenarios y stress tests.
- [DeMiguel, Garlappi y Uppal, Optimal Versus Naive Diversification](https://ideas.repec.org/a/oup/rfinst/v22y2009i5p1915-1953.html):
  benchmark obligatorio de `1/N` y advertencia sobre error de estimacion.
- [PyPortfolioOpt](https://github.com/PyPortfolio/PyPortfolioOpt): referencia
  popular para minimum variance, Black-Litterman, shrinkage y HRP.
- [Riskfolio-Lib](https://github.com/dcajasn/Riskfolio-Lib): referencia para
  risk parity, drawdown y multiples medidas convexas de riesgo.
- [cvxportfolio](https://github.com/cvxgrp/cvxportfolio): referencia para
  costos, restricciones y optimizacion multi-periodo.
- [skfolio](https://github.com/skfolio/skfolio): referencia para evaluacion
  compatible con workflows out-of-sample y seleccion de modelos.

Las estrellas miden adopcion, no calidad de una estrategia ni rentabilidad.

## Baseline aceptado

| Item | Politica |
| --- | --- |
| Universo | activos aprobados por perfil, datos, comite y riesgo |
| Direccion | long-only, sin leverage por defecto |
| Default | inverse volatility con caps y cash |
| Benchmarks | `1/N`, inverse volatility y no rebalancear |
| Historia | alerta bajo 60 ruedas; 252 deseables; probar multiples regimenes |
| Covarianza opcional | Ledoit-Wolf para minimum variance |
| Volatilidad maxima | la definida por el perfil; actualmente 18% anual |
| Tail risk | VaR y Expected Shortfall historicos 95% |
| Drawdown | trayectoria compuesta point-in-time |
| Concentracion | caps por activo, sector, pais, asset class y moneda |
| Diversificacion | numero efectivo `1 / sum(w_i^2)` y risk contributions |
| Rebalanceo | banda mayor entre 1 punto porcentual y 20% del peso |
| Ejecucion | ventas obligatorias ignoran banda; resto respeta no-trade zone |

Los 60/252 dias y las bandas son parametros operativos iniciales, no constantes
economicas. En una cuenta imponible las bandas deben contrastarse contra spread,
impuestos y beneficio esperado del rebalanceo.

## Cambios implementados

- El limite de volatilidad escala proporcionalmente activos riesgosos hacia cash.
- `AllocationResult` registra observaciones, VaR, Expected Shortfall, drawdown,
  numero efectivo, turnover, contribuciones al riesgo y exposiciones agrupadas.
- PyPortfolioOpt usa Ledoit-Wolf; Riskfolio solicita covariance Ledoit.
- Perfil y constraints aceptan caps por asset class y moneda.
- Metadata y claves de limites se normalizan de forma consistente.
- El RiskAgent trata warnings y hard breaches por separado, controla drawdown y
  exposiciones agregadas, y deja score neutral cuando aprueba.
- Comparables y DCF llegan al comite como factores separados; el score relativo
  ya no vuelve a contar el DCF blended.
- Pesos del comite: fundamental 55%, comparables 25%, tecnico 20%, riesgo 0% mas
  veto. La dispersion reduce confianza y baja a `hold` una accion poco confiable.

## Validacion pendiente antes de usar capital

1. Retornos alineados por calendario y moneda, sin forward-fill de activos cerrados.
2. Walk-forward contra `1/N`, inverse volatility y portfolio actual.
3. Costos, impuestos uruguayos, spread y turnover realizados.
4. Stress historico e hipotetico por factores; opciones requieren delta, gamma y vega.
5. Bootstrap de pesos, risk contributions y estabilidad de caps.
6. Sensibilidad de ventanas 60/126/252/504 y bandas de rebalanceo.
7. Paper portfolio y reconciliacion diaria con SnapTrade antes de ordenes.

La ausencia de estas validaciones limita confianza; no se reemplaza con un Sharpe
in-sample ni con una frontera eficiente visualmente atractiva.

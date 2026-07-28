# Investement

Investement es un sistema de agentes para asistir en la construccion, analisis y gestion de un portfolio de inversion personalizado.

El objetivo es desarrollar un asesor de inversion que pueda recomendar compras, ventas, desinversiones y rebalanceos en base a analisis fundamental, analisis tecnico, gestion de riesgo y optimizacion de portfolio. En etapas posteriores, el sistema deberia integrarse con Charles Schwab para leer cuentas, consultar datos de mercado y eventualmente ejecutar trades de forma controlada.

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

Para la integracion con Schwab, se evaluara el Schwab Trader API, que ofrece OAuth y endpoints para cuentas, market data y ordenes. El acceso debe validarse desde developer.schwab.com.

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

### Agente Ejecutor Schwab

Responsable de conectar con Charles Schwab para consultar cuenta y eventualmente operar.

Fases previstas:

1. Solo lectura de cuenta y posiciones.
2. Simulacion de ordenes.
3. Generacion de ordenes pendientes.
4. Confirmacion humana obligatoria.
5. Ejecucion real.
6. Registro completo de cada operacion.

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
9. Evaluar integracion Schwab en modo lectura.
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

## Estado Actual

Proyecto en fase inicial de definicion.

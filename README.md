# Investement

Investement es un sistema de agentes para asistir en la construccion, analisis y gestion de un portfolio de inversion personalizado.

## Dashboard Web

El repo incluye una app Next.js lista para alojar en Vercel. El dashboard separa
Resumen, Rendimiento, Posiciones y Noticias, e incluye valor total con efectivo,
P&L, atribucion diaria, asignacion por estrategia, concentracion, riesgo, tablas
filtrables y comparacion contra un benchmark ponderado por exposicion. La
descomposicion agrupa las posiciones en categorias desplegables. La vista de
Posiciones tambien calcula stops sugeridos por instrumento para control de
riesgo, sin enviar ordenes al broker.

Los stops sugeridos son una referencia operativa, no ordenes automaticas. La
regla combina volatilidad realizada de las ultimas ruedas con un rango por tipo
de activo: ETFs usan buffers mas estrechos, acciones value/dividend quedan en
un rango intermedio y acciones growth/foreign tienen mas espacio. Cuando una
posicion acumula una ganancia amplia, el stop intenta proteger parte de esa
ganancia sin poner el nivel por encima del precio actual.

Noticias combina cobertura reciente de Google News RSS con el calendario de
earnings y dividendos de Nasdaq. La vista muestra el ultimo mes por posicion,
el contexto global de la ultima semana y los proximos eventos de la cartera.

Los saldos y posiciones actuales provienen de SnapTrade. La serie historica
reconstruye el comportamiento de la composicion actual; no representa el
historial oficial de flujos y saldos del broker.

En desarrollo local, si no hay variables de SnapTrade, la app puede leer un
snapshot local en `portfolio.config.json`:

- `holdings`: posiciones actuales, cantidad y costo base opcional.
- `cash`: efectivo disponible en la moneda base.
- `benchmark`: simbolo de referencia, por defecto `SPY`.
- `similarPortfolios`: blends comparables para medir rendimiento y correlacion.

Para correrla localmente en una maquina con Node.js:

```bash
npm install
npm run dev
```

Para desplegarla, importar el repositorio en Vercel. Vercel detecta Next.js con
[`vercel.json`](vercel.json) y ejecuta el build automaticamente. La API
`/api/market` consulta Yahoo Chart desde serverless functions y cachea por un
minuto. La API `/api/portfolio` lee SnapTrade Personal en modo read-only cuando
existen estas variables de entorno:

- `SNAPTRADE_CLIENT_ID`
- `SNAPTRADE_CONSUMER_KEY`
- `PORTFOLIO_BASE_CURRENCY`, por defecto `USD`
- `PORTFOLIO_BENCHMARK`, por defecto `SPY`

### Informe semanal

Vercel ejecuta `/api/cron/weekly-report` los domingos a las 15:00 UTC, que
corresponde a las 12:00 en Montevideo. El correo incluye resumen de rendimiento,
compras y ventas leidas de SnapTrade y eventos relevantes de la proxima semana.

Configurar estas variables solo en Vercel:

- `CRON_SECRET`: secreto largo y aleatorio para proteger la ruta del cron.
- `SMTP_HOST` y `SMTP_PORT`: servidor SMTP, por ejemplo
  `smtp-mail.outlook.com` y `587`.
- `SMTP_SECURE`: `false` para STARTTLS en puerto 587; `true` para puerto 465.
- `SMTP_USERNAME` y `SMTP_PASSWORD`: credenciales SMTP o app password.
- `SMTP_FROM`: remitente autorizado, normalmente igual a `SMTP_USERNAME`.
- `WEEKLY_REPORT_TO`: uno o mas destinatarios separados por coma.
- `WEEKLY_REPORT_TIMEZONE`: `America/Montevideo` por defecto.

Vercel envia `CRON_SECRET` como `Authorization: Bearer ...`. En el plan Hobby,
la ejecucion puede ocurrir dentro de la hora programada; los planes con cron de
precision por minuto lo envian a las 12:00.

`portfolio.config.json` queda ignorado por Git porque puede revelar posiciones
personales. Para regenerar un snapshot local desde SnapTrade:

```bash
.venv/bin/python scripts/export_snaptrade_dashboard_config.py
```

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

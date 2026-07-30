# Auditoria de broker, auditor y orquestacion

Fecha de revision: 2026-07-29.

## Principio

La primera version puede leer y recomendar, pero no ejecutar. La seguridad se
implementa por ausencia de capacidades de ordenes, no solo por una bandera. Los
logs son evidencia sensible: requieren integridad y tambien confidencialidad.

## Fuentes

- [SnapTrade, Rate Limiting](https://docs.snaptrade.com/docs/ratelimiting): dos
  niveles de rate limit, headers de reset, backoff y jitter para HTTP 429.
- [SnapTrade, Sending Requests](https://docs.snaptrade.com/docs/requests):
  firmas, `x-request-id` y headers de limite.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html):
  no registrar tokens, passwords, claves, cuentas ni PII innecesaria; proteger
  integridad, confidencialidad y disponibilidad.
- [OWASP Secrets Management](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html):
  secretos fuera de logs y gestionados mediante un store dedicado.
- [Prefect](https://github.com/PrefectHQ/prefect) y
  [Dagster](https://github.com/dagster-io/dagster): referencias populares para
  dependencias, observabilidad, retries y versionado de workflows.

## Contratos implementados

### Broker

- Solo expone accounts, balances, positions y portfolio.
- No existen metodos `place_order` ni `cancel_order`.
- Solo acepta `https://api.snaptrade.com`, timeout de 0-120 segundos y hasta
  cinco retries configurables; baseline dos.
- HTTP 429 usa primero headers de reset y luego backoff acotado.
- Errores conservan operation, status, code y request id sin body ni secretos.
- Cuenta normalizada rechaza monedas mezcladas e instrumentos sin valuador.

### Auditor

- Redaccion profunda para claves, tokens, credentials, client IDs, firmas,
  cookies y numeros de cuenta, incluso sin usar `AuditorAgent`.
- JSON canonico y cadena SHA-256 tamper-evident.
- Cada linea se agrega en una unica escritura y se fuerza a disco.
- Memoria usa claves validadas y escritura atomica.

La cadena detecta alteraciones accidentales o posteriores, pero no reemplaza una
firma externa: alguien con control total del archivo podria recalcular toda la
cadena. Para produccion se requiere checkpoint firmado o almacenamiento WORM.

### Orquestacion

- Dependencias desconocidas o ciclicas fallan antes de ejecutar.
- Cada step declara version; el inicio registra `as_of`, claves de input,
  dependencias y versiones.
- Inicio, resultado y falla quedan auditados.
- El comite persiste pesos efectivos, disenso y veto.

## Siguiente gate operativo

Antes de habilitar simulacion de ordenes: cache con TTL para snapshots de broker,
jitter de retries, checkpoint externo del audit log, limites de tamano/precio,
estimacion de implementation shortfall, idempotency keys, approval humano y
reconciliacion post-trade. Ninguna de estas capacidades justifica agregar
ejecucion al cliente Personal read-only actual.

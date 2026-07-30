---
name: broker-read-only
description: Audit or modify the SnapTrade Personal read-only broker boundary, normalization, retries, secret handling, and portfolio reconciliation.
---

# Broker Read Only

Read `../../investigacion/auditoria_agentes_operativos.md` and current SnapTrade
documentation before changing authentication or endpoints.

Expose only account, balance, position and portfolio reads. Do not add order,
cancel or replace methods to the read-only client. Reject non-SnapTrade hosts,
non-HTTPS URLs, mixed currencies, missing symbols and unsupported instruments.

Keep `clientId` and `consumerKey` in macOS Keychain, hidden from repr, logs,
exceptions and audit payloads. Safe errors include operation, HTTP status, error
code and request ID only.

For HTTP 429, honor account/customer reset headers, then bounded exponential
backoff. Bound timeout and retries. Avoid aggressive polling; cache and
reconcile snapshots when freshness requirements permit.

Portfolio normalization must reconcile reported total, cash, supported position
values and residual unclassified value. Never infer unsupported derivative value
or FX conversion. The target portfolio remains independent from current broker
allocation during initial construction.

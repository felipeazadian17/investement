---
name: investment-governance
description: Audit or modify investment committee weighting, evidence independence, dissent, vetoes, workflow dependencies, versioning, and decision auditability.
---

# Investment Governance

Read both `../../investigacion/auditoria_portfolio_riesgo_gobernanza.md` and
`../../investigacion/auditoria_agentes_operativos.md`.

## Committee

Keep independent evidence separate. DCF/fundamental has 55% policy weight,
comparable valuation 25%, technical 20%, and risk zero directional weight plus
veto. Do not score a blended DCF/comparable value again beside the DCF.

Normalize weights across available findings, multiply by calibrated confidence,
record effective weights and material dissent, and reduce confidence for
dispersion. Convert an otherwise actionable result to hold when confidence is
below the policy floor. A veto always blocks action.

Parameters are governance policy, not empirically optimal constants. Recalibrate
only with out-of-sample decision outcomes and preserve the old policy/version for
comparison.

## Workflow

Reject missing dependencies, duplicate names and cycles before side effects.
Version every step and record run ID, `as_of`, dependency graph, starts, outputs,
failures and execution order. Never place secrets in inputs or outputs intended
for audit. Keep calculations deterministic and LLM narration downstream.

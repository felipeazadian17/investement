from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite

from investement.domain import SignalAction


@dataclass(frozen=True)
class ValuationSignal:
    action: SignalAction
    current_price: float
    fair_value: float
    margin_of_safety: float
    confidence: float
    risks: Sequence[str]
    invalidation_conditions: Sequence[str]


def valuation_signal(
    current_price: float,
    fair_value: float,
    confidence: float,
    required_margin: float = 0.20,
    sell_premium: float = 0.20,
    risks: Sequence[str] = (),
    invalidation_conditions: Sequence[str] = (),
) -> ValuationSignal:
    for value, name in ((current_price, "current_price"), (fair_value, "fair_value")):
        if not isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be positive and finite")
    if not 0 <= confidence <= 1:
        raise ValueError("confidence must be between 0 and 1")
    if not 0 <= required_margin < 1 or not 0 <= sell_premium < 1:
        raise ValueError("thresholds must be between 0 and 1")

    margin = (fair_value - current_price) / fair_value
    premium = (current_price - fair_value) / fair_value
    if margin >= required_margin:
        action = SignalAction.BUY
    elif premium >= sell_premium:
        action = SignalAction.SELL
    elif premium > 0:
        action = SignalAction.REDUCE
    else:
        action = SignalAction.HOLD
    return ValuationSignal(
        action=action,
        current_price=current_price,
        fair_value=fair_value,
        margin_of_safety=margin,
        confidence=confidence,
        risks=tuple(risks),
        invalidation_conditions=tuple(invalidation_conditions),
    )

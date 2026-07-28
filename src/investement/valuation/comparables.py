from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from math import isfinite
from statistics import median


@dataclass(frozen=True)
class ComparableObservation:
    symbol: str
    multiple: float
    metric: str

    def __post_init__(self) -> None:
        if not self.symbol.strip() or not self.metric.strip():
            raise ValueError("symbol and metric are required")
        if not isfinite(self.multiple) or self.multiple <= 0:
            raise ValueError("comparable multiple must be positive and finite")


@dataclass(frozen=True)
class RelativeValuationResult:
    metric: str
    target_metric_value: float
    selected_multiple: float
    value_per_share: float
    peer_count: int
    excluded_outliers: Sequence[str]


def value_from_comparables(
    target_metric_value: float,
    observations: Iterable[ComparableObservation],
    metric: str,
    outlier_mad_limit: float | None = 3.5,
) -> RelativeValuationResult:
    if not isfinite(target_metric_value) or target_metric_value <= 0:
        raise ValueError("target_metric_value must be positive and finite")
    selected = [item for item in observations if item.metric.lower() == metric.lower()]
    if len(selected) < 2:
        raise ValueError("at least two comparable observations are required")

    multiples = [item.multiple for item in selected]
    center = median(multiples)
    absolute_deviations = [abs(value - center) for value in multiples]
    mad = median(absolute_deviations)
    kept = selected
    excluded = []
    if outlier_mad_limit is not None and mad > 0:
        scale = 1.4826 * mad
        kept = [
            item for item in selected if abs(item.multiple - center) / scale <= outlier_mad_limit
        ]
        excluded = [item.symbol for item in selected if item not in kept]
    if len(kept) < 2:
        raise ValueError("outlier filtering left fewer than two peers")

    selected_multiple = median([item.multiple for item in kept])
    return RelativeValuationResult(
        metric=metric,
        target_metric_value=target_metric_value,
        selected_multiple=selected_multiple,
        value_per_share=target_metric_value * selected_multiple,
        peer_count=len(kept),
        excluded_outliers=tuple(excluded),
    )

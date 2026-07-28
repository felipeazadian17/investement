from collections.abc import Mapping, Sequence

from investement.portfolio.models import AssetMetadata, PortfolioConstraints

_TOLERANCE = 1e-10


def project_weights(
    scores: Mapping[str, float],
    constraints: PortfolioConstraints,
    metadata: Mapping[str, AssetMetadata],
) -> Mapping[str, float]:
    assets = tuple(scores)
    if not assets:
        raise ValueError("scores cannot be empty")
    target = 1.0 - constraints.min_cash
    minimum = constraints.min_weight
    if len(assets) * minimum > target + _TOLERANCE:
        raise ValueError("minimum weights exceed investable capital")
    if sum(_asset_limit(asset, constraints) for asset in assets) < target - _TOLERANCE:
        raise ValueError("asset caps make the allocation infeasible")

    weights = {asset: minimum for asset in assets}
    _validate_group_minimums(weights, constraints, metadata)
    remaining = target - sum(weights.values())
    positive_scores = {asset: max(float(scores[asset]), 0.0) for asset in assets}

    for _ in range(len(assets) * 6 + 10):
        if remaining <= _TOLERANCE:
            break
        capacities = {
            asset: _available_capacity(asset, weights, constraints, metadata) for asset in assets
        }
        candidates = [asset for asset, capacity in capacities.items() if capacity > _TOLERANCE]
        if not candidates:
            raise ValueError("group caps make the allocation infeasible")
        score_total = sum(positive_scores[asset] for asset in candidates)
        if score_total <= _TOLERANCE:
            proportions = {asset: 1.0 / len(candidates) for asset in candidates}
        else:
            proportions = {asset: positive_scores[asset] / score_total for asset in candidates}
        additions = {
            asset: min(remaining * proportions[asset], capacities[asset]) for asset in candidates
        }
        _scale_additions_to_group_capacity(
            additions,
            weights,
            metadata,
            "sector",
            constraints.sector_max_weights,
        )
        _scale_additions_to_group_capacity(
            additions,
            weights,
            metadata,
            "country",
            constraints.country_max_weights,
        )
        progress = sum(additions.values())
        if progress <= _TOLERANCE:
            raise ValueError("unable to project weights within constraints")
        for asset, addition in additions.items():
            weights[asset] += addition
        remaining -= progress

    if remaining > 1e-8:
        raise ValueError("unable to allocate all investable capital")
    return {asset: _clean(weight) for asset, weight in weights.items()}


def validate_weights(
    weights: Mapping[str, float],
    constraints: PortfolioConstraints,
    metadata: Mapping[str, AssetMetadata],
) -> Sequence[str]:
    violations = []
    target = 1.0 - constraints.min_cash
    if abs(sum(weights.values()) - target) > 1e-7:
        violations.append("weights do not sum to investable capital")
    for asset, weight in weights.items():
        if weight < constraints.min_weight - 1e-8:
            violations.append(f"{asset} is below its minimum weight")
        if weight > _asset_limit(asset, constraints) + 1e-8:
            violations.append(f"{asset} exceeds its maximum weight")
    violations.extend(
        _group_violations(weights, metadata, "sector", constraints.sector_max_weights)
    )
    violations.extend(
        _group_violations(weights, metadata, "country", constraints.country_max_weights)
    )
    return tuple(violations)


def _asset_limit(asset: str, constraints: PortfolioConstraints) -> float:
    return min(constraints.max_weight, constraints.asset_max_weights.get(asset, 1.0))


def _available_capacity(
    asset: str,
    weights: Mapping[str, float],
    constraints: PortfolioConstraints,
    metadata: Mapping[str, AssetMetadata],
) -> float:
    capacity = _asset_limit(asset, constraints) - weights[asset]
    asset_metadata = metadata.get(asset, AssetMetadata())
    if asset_metadata.sector in constraints.sector_max_weights:
        used = sum(
            weight
            for candidate, weight in weights.items()
            if metadata.get(candidate, AssetMetadata()).sector == asset_metadata.sector
        )
        capacity = min(capacity, constraints.sector_max_weights[asset_metadata.sector] - used)
    if asset_metadata.country in constraints.country_max_weights:
        used = sum(
            weight
            for candidate, weight in weights.items()
            if metadata.get(candidate, AssetMetadata()).country == asset_metadata.country
        )
        capacity = min(capacity, constraints.country_max_weights[asset_metadata.country] - used)
    return max(capacity, 0.0)


def _validate_group_minimums(
    weights: Mapping[str, float],
    constraints: PortfolioConstraints,
    metadata: Mapping[str, AssetMetadata],
) -> None:
    violations = _group_violations(
        weights, metadata, "sector", constraints.sector_max_weights
    ) + _group_violations(weights, metadata, "country", constraints.country_max_weights)
    if violations:
        raise ValueError(f"minimum weights conflict with group caps: {'; '.join(violations)}")


def _group_violations(
    weights: Mapping[str, float],
    metadata: Mapping[str, AssetMetadata],
    attribute: str,
    limits: Mapping[str, float],
) -> list:
    violations = []
    for group, limit in limits.items():
        total = sum(
            weight
            for asset, weight in weights.items()
            if getattr(metadata.get(asset, AssetMetadata()), attribute) == group
        )
        if total > limit + 1e-8:
            violations.append(f"{attribute} {group} exceeds {limit:.4f}")
    return violations


def _scale_additions_to_group_capacity(
    additions: dict,
    weights: Mapping[str, float],
    metadata: Mapping[str, AssetMetadata],
    attribute: str,
    limits: Mapping[str, float],
) -> None:
    for group, limit in limits.items():
        members = [
            asset
            for asset in additions
            if getattr(metadata.get(asset, AssetMetadata()), attribute) == group
        ]
        proposed = sum(additions[asset] for asset in members)
        if proposed <= _TOLERANCE:
            continue
        used = sum(
            weight
            for asset, weight in weights.items()
            if getattr(metadata.get(asset, AssetMetadata()), attribute) == group
        )
        available = max(limit - used, 0.0)
        if proposed > available:
            scale = available / proposed
            for asset in members:
                additions[asset] *= scale


def _clean(value: float) -> float:
    return 0.0 if abs(value) < 1e-12 else float(value)

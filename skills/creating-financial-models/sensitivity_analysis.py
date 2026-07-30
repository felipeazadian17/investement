"""State-safe sensitivity and scenario helpers for financial models."""

from collections.abc import Callable, Mapping, Sequence
from math import isclose
from typing import Any

import numpy as np
import pandas as pd


class SensitivityAnalyzer:
    """Run sensitivities while restoring the caller's base state."""

    def __init__(self, base_model: Any = None) -> None:
        self.base_model = base_model

    def one_way_sensitivity(
        self,
        variable_name: str,
        base_value: float,
        test_values: Sequence[float],
        output_func: Callable[[], float],
        update_func: Callable[[float], None],
        validator: Callable[[float], bool] | None = None,
    ) -> pd.DataFrame:
        base_output = float(output_func())
        rows = []
        try:
            for value in test_values:
                valid = validator(value) if validator is not None else True
                if not valid:
                    rows.append(_invalid_row(variable_name, value))
                    continue
                update_func(value)
                output = float(output_func())
                rows.append(
                    {
                        "variable": variable_name,
                        "value": value,
                        "valid": True,
                        "output": output,
                        "output_change": output - base_output,
                        "output_change_pct": _percent_change(output, base_output),
                    }
                )
        finally:
            update_func(base_value)
        return pd.DataFrame(rows)

    def two_way_sensitivity(
        self,
        row_name: str,
        row_base: float,
        row_values: Sequence[float],
        column_name: str,
        column_base: float,
        column_values: Sequence[float],
        output_func: Callable[[], float],
        update_func: Callable[[float, float], None],
        validator: Callable[[float, float], bool] | None = None,
    ) -> pd.DataFrame:
        results = np.full((len(row_values), len(column_values)), np.nan)
        try:
            for row_index, row_value in enumerate(row_values):
                for column_index, column_value in enumerate(column_values):
                    valid = (
                        validator(row_value, column_value)
                        if validator is not None
                        else True
                    )
                    if not valid:
                        continue
                    update_func(row_value, column_value)
                    results[row_index, column_index] = float(output_func())
        finally:
            update_func(row_base, column_base)
        return pd.DataFrame(
            results,
            index=pd.Index(row_values, name=row_name),
            columns=pd.Index(column_values, name=column_name),
        )

    def tornado_analysis(
        self,
        variables: Mapping[str, Mapping[str, Any]],
        output_func: Callable[[], float],
    ) -> pd.DataFrame:
        base_output = float(output_func())
        rows = []
        for name, specification in variables.items():
            update = specification["update_func"]
            base = float(specification["base"])
            try:
                update(float(specification["low"]))
                low_output = float(output_func())
                update(float(specification["high"]))
                high_output = float(output_func())
            finally:
                update(base)
            rows.append(
                {
                    "variable": name,
                    "base_value": base,
                    "low_value": specification["low"],
                    "high_value": specification["high"],
                    "low_output": low_output,
                    "high_output": high_output,
                    "low_delta": low_output - base_output,
                    "high_delta": high_output - base_output,
                    "impact": abs(high_output - low_output),
                }
            )
        return pd.DataFrame(rows).sort_values("impact", ascending=False)

    def scenario_analysis(
        self,
        scenarios: Mapping[str, Mapping[str, float]],
        variable_updates: Mapping[str, Callable[[float], None]],
        base_values: Mapping[str, float],
        output_func: Callable[[], float],
        probability_weights: Mapping[str, float],
    ) -> pd.DataFrame:
        _validate_scenarios(scenarios, variable_updates, base_values, probability_weights)
        rows = []
        try:
            for scenario, variables in scenarios.items():
                _restore(variable_updates, base_values)
                for variable, value in variables.items():
                    variable_updates[variable](value)
                output = float(output_func())
                probability = probability_weights[scenario]
                rows.append(
                    {
                        "scenario": scenario,
                        "probability": probability,
                        "output": output,
                        "weighted_output": output * probability,
                        **variables,
                    }
                )
        finally:
            _restore(variable_updates, base_values)
        frame = pd.DataFrame(rows)
        frame.attrs["expected_value"] = float(frame["weighted_output"].sum())
        return frame


def create_data_table(
    row_name: str,
    row_base: float,
    row_values: Sequence[float],
    row_update: Callable[[float], None],
    column_name: str,
    column_base: float,
    column_values: Sequence[float],
    column_update: Callable[[float], None],
    output_func: Callable[[], float],
    validator: Callable[[float, float], bool] | None = None,
) -> pd.DataFrame:
    results = np.full((len(row_values), len(column_values)), np.nan)
    try:
        for row_index, row_value in enumerate(row_values):
            for column_index, column_value in enumerate(column_values):
                valid = (
                    validator(row_value, column_value)
                    if validator is not None
                    else True
                )
                if not valid:
                    continue
                row_update(row_value)
                column_update(column_value)
                results[row_index, column_index] = float(output_func())
    finally:
        row_update(row_base)
        column_update(column_base)
    return pd.DataFrame(
        results,
        index=pd.Index(row_values, name=row_name),
        columns=pd.Index(column_values, name=column_name),
    )


def _invalid_row(variable_name: str, value: float) -> dict[str, Any]:
    return {
        "variable": variable_name,
        "value": value,
        "valid": False,
        "output": np.nan,
        "output_change": np.nan,
        "output_change_pct": np.nan,
    }


def _percent_change(output: float, base_output: float) -> float:
    return (output / base_output - 1) if base_output else np.nan


def _restore(
    variable_updates: Mapping[str, Callable[[float], None]],
    base_values: Mapping[str, float],
) -> None:
    for variable, value in base_values.items():
        variable_updates[variable](value)


def _validate_scenarios(
    scenarios: Mapping[str, Mapping[str, float]],
    variable_updates: Mapping[str, Callable[[float], None]],
    base_values: Mapping[str, float],
    probability_weights: Mapping[str, float],
) -> None:
    if not scenarios:
        raise ValueError("at least one scenario is required")
    if set(probability_weights) != set(scenarios):
        raise ValueError("every scenario requires exactly one probability")
    if any(value < 0 for value in probability_weights.values()) or not isclose(
        sum(probability_weights.values()),
        1.0,
        abs_tol=1e-9,
    ):
        raise ValueError("scenario probabilities must be non-negative and sum to one")
    variables = {name for values in scenarios.values() for name in values}
    if not variables <= set(variable_updates) or not variables <= set(base_values):
        raise ValueError("every scenario variable requires an update function and base value")


if __name__ == "__main__":
    class SimpleModel:
        revenue = 1000.0
        margin = 0.20

        def value(self) -> float:
            return self.revenue * self.margin * 10

    model = SimpleModel()
    analyzer = SensitivityAnalyzer(model)
    table = analyzer.two_way_sensitivity(
        row_name="margin",
        row_base=model.margin,
        row_values=(0.15, 0.20, 0.25),
        column_name="revenue",
        column_base=model.revenue,
        column_values=(800.0, 1000.0, 1200.0),
        output_func=model.value,
        update_func=lambda margin, revenue: (
            setattr(model, "margin", margin),
            setattr(model, "revenue", revenue),
        ),
    )
    print(table)

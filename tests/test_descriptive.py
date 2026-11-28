from __future__ import annotations

import math

from kitty.descriptive import calculate_descriptive
from kitty.validation import NumericDataset


def _dataset() -> NumericDataset:
    return NumericDataset(
        sample_ids=("s1", "s2", "s3", "s4"),
        sample_names=("A1", "A2", "B1", "B2"),
        variable_ids=("v1", "v2"),
        variable_names=("Variable 1", "Variable 2"),
        classes=("A", "A", "B", "B"),
        values=((0.0, 10.0), (2.0, 12.0), (4.0, 14.0), (6.0, 16.0)),
    )


def test_descriptive_statistics_are_calculated_by_variable_and_class() -> None:
    result = calculate_descriptive(_dataset())

    summaries = result.for_variable("v1")

    assert [summary.class_name for summary in summaries] == ["A", "B"]
    assert summaries[0].n == 2
    assert summaries[0].mean == 1.0
    assert math.isclose(summaries[0].standard_deviation or 0, math.sqrt(2))
    assert summaries[0].zero_count == 1
    assert summaries[1].mean == 5.0
    assert math.isclose(summaries[1].standard_deviation or 0, math.sqrt(2))


def test_class_order_follows_first_appearance() -> None:
    dataset = NumericDataset(
        sample_ids=("s1", "s2", "s3"),
        sample_names=("B1", "A1", "C1"),
        variable_ids=("v1",),
        variable_names=("Variable",),
        classes=("B", "A", "C"),
        values=((1.0,), (2.0,), (3.0,)),
    )

    summaries = calculate_descriptive(dataset).for_variable("v1")

    assert [summary.class_name for summary in summaries] == ["B", "A", "C"]
    assert all(summary.standard_deviation is None for summary in summaries)

from __future__ import annotations

import statistics
from dataclasses import dataclass

from kitty.validation import NumericDataset


@dataclass(frozen=True)
class GroupSummary:
    variable_id: str
    variable_name: str
    class_name: str
    n: int
    mean: float
    standard_deviation: float | None
    zero_count: int


@dataclass(frozen=True)
class DescriptiveResult:
    summaries: tuple[GroupSummary, ...]
    variable_ids: tuple[str, ...]
    variable_names: tuple[str, ...]

    def for_variable(self, variable_id: str) -> tuple[GroupSummary, ...]:
        return tuple(
            summary
            for summary in self.summaries
            if summary.variable_id == variable_id
        )


def calculate_descriptive(dataset: NumericDataset) -> DescriptiveResult:
    class_order = tuple(dict.fromkeys(dataset.classes))
    summaries: list[GroupSummary] = []

    for column, (variable_id, variable_name) in enumerate(
        zip(dataset.variable_ids, dataset.variable_names)
    ):
        for class_name in class_order:
            values = [
                row[column]
                for row, sample_class in zip(dataset.values, dataset.classes)
                if sample_class == class_name
            ]
            summaries.append(
                GroupSummary(
                    variable_id=variable_id,
                    variable_name=variable_name,
                    class_name=class_name,
                    n=len(values),
                    mean=statistics.fmean(values),
                    standard_deviation=(
                        statistics.stdev(values) if len(values) >= 2 else None
                    ),
                    zero_count=sum(value == 0 for value in values),
                )
            )

    return DescriptiveResult(
        summaries=tuple(summaries),
        variable_ids=dataset.variable_ids,
        variable_names=dataset.variable_names,
    )

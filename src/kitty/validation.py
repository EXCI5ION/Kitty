from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from kitty.project import ProjectState


Severity = Literal["error", "warning"]


@dataclass(frozen=True)
class ValidationIssue:
    severity: Severity
    code: str
    message: str


@dataclass(frozen=True)
class NumericDataset:
    sample_ids: tuple[str, ...]
    sample_names: tuple[str, ...]
    variable_ids: tuple[str, ...]
    variable_names: tuple[str, ...]
    classes: tuple[str, ...]
    values: tuple[tuple[float, ...], ...]


@dataclass(frozen=True)
class ValidationReport:
    dataset: NumericDataset | None
    issues: tuple[ValidationIssue, ...]
    included_samples: int
    included_variables: int
    zero_count: int
    negative_count: int
    constant_variables: tuple[str, ...]

    @property
    def errors(self) -> tuple[ValidationIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == "error")

    @property
    def warnings(self) -> tuple[ValidationIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == "warning")

    @property
    def is_valid(self) -> bool:
        return self.dataset is not None and not self.errors


def validate_project(project: ProjectState) -> ValidationReport:
    sample_indices = [
        index for index, sample in enumerate(project.samples) if sample.included
    ]
    variable_indices = [
        index for index, variable in enumerate(project.variables) if variable.included
    ]
    issues: list[ValidationIssue] = []

    if not sample_indices:
        issues.append(
            ValidationIssue("error", "no_samples", "No hay muestras incluidas.")
        )
    if not variable_indices:
        issues.append(
            ValidationIssue("error", "no_variables", "No hay variables incluidas.")
        )

    unclassified = [
        project.samples[index].display_name
        for index in sample_indices
        if not project.samples[index].class_name.strip()
    ]
    if unclassified:
        issues.append(
            ValidationIssue(
                "error",
                "unclassified_samples",
                _counted_examples(
                    "muestra sin clase",
                    "muestras sin clase",
                    unclassified,
                ),
            )
        )

    class_counts: dict[str, int] = {}
    for index in sample_indices:
        class_name = project.samples[index].class_name.strip()
        if class_name:
            class_counts[class_name] = class_counts.get(class_name, 0) + 1
    if len(class_counts) < 2:
        issues.append(
            ValidationIssue(
                "error",
                "insufficient_classes",
                "Se necesitan al menos dos clases entre las muestras incluidas.",
            )
        )
    small_classes = [name for name, count in class_counts.items() if count < 2]
    if small_classes:
        issues.append(
            ValidationIssue(
                "warning",
                "small_classes",
                _counted_examples(
                    "clase con menos de dos muestras",
                    "clases con menos de dos muestras",
                    small_classes,
                ),
            )
        )

    blank_cells: list[str] = []
    nonnumeric_cells: list[str] = []
    nonfinite_cells: list[str] = []
    numeric_rows: list[list[float]] = []
    zero_count = 0
    negative_count = 0

    for sample_index in sample_indices:
        sample = project.samples[sample_index]
        numeric_row: list[float] = []
        for variable_index in variable_indices:
            variable = project.variables[variable_index]
            raw_value = project.matrix.values[sample_index][variable_index].strip()
            location = f"{sample.display_name} / {variable.display_name}"
            if not raw_value:
                blank_cells.append(location)
                numeric_row.append(math.nan)
                continue
            try:
                value = float(raw_value)
            except ValueError:
                nonnumeric_cells.append(f"{location}: «{raw_value}»")
                numeric_row.append(math.nan)
                continue
            if not math.isfinite(value):
                nonfinite_cells.append(f"{location}: «{raw_value}»")
                numeric_row.append(math.nan)
                continue
            if value == 0:
                zero_count += 1
            elif value < 0:
                negative_count += 1
            numeric_row.append(value)
        numeric_rows.append(numeric_row)

    for code, singular, plural, examples in (
        ("blank_cells", "celda vacía", "celdas vacías", blank_cells),
        (
            "nonnumeric_cells",
            "celda no numérica",
            "celdas no numéricas",
            nonnumeric_cells,
        ),
        (
            "nonfinite_cells",
            "valor no finito",
            "valores no finitos",
            nonfinite_cells,
        ),
    ):
        if examples:
            issues.append(
                ValidationIssue(
                    "error",
                    code,
                    _counted_examples(singular, plural, examples),
                )
            )

    constant_variables: list[str] = []
    if numeric_rows and not (blank_cells or nonnumeric_cells or nonfinite_cells):
        for column, variable_index in enumerate(variable_indices):
            values = {row[column] for row in numeric_rows}
            if len(values) == 1:
                constant_variables.append(
                    project.variables[variable_index].display_name
                )
    if constant_variables:
        issues.append(
            ValidationIssue(
                "warning",
                "constant_variables",
                _counted_examples(
                    "variable constante",
                    "variables constantes",
                    constant_variables,
                ),
            )
        )
    if negative_count:
        issues.append(
            ValidationIssue(
                "warning",
                "negative_values",
                f"Se encontraron {negative_count} valores negativos.",
            )
        )

    has_errors = any(issue.severity == "error" for issue in issues)
    dataset = None
    if not has_errors:
        dataset = NumericDataset(
            sample_ids=tuple(project.samples[index].internal_id for index in sample_indices),
            sample_names=tuple(
                project.samples[index].display_name for index in sample_indices
            ),
            variable_ids=tuple(
                project.variables[index].internal_id for index in variable_indices
            ),
            variable_names=tuple(
                project.variables[index].display_name for index in variable_indices
            ),
            classes=tuple(
                project.samples[index].class_name.strip() for index in sample_indices
            ),
            values=tuple(tuple(row) for row in numeric_rows),
        )

    return ValidationReport(
        dataset=dataset,
        issues=tuple(issues),
        included_samples=len(sample_indices),
        included_variables=len(variable_indices),
        zero_count=zero_count,
        negative_count=negative_count,
        constant_variables=tuple(constant_variables),
    )


def _counted_examples(singular: str, plural: str, examples: list[str]) -> str:
    label = singular if len(examples) == 1 else plural
    preview = "; ".join(examples[:3])
    remainder = len(examples) - 3
    suffix = f"; y {remainder} más" if remainder > 0 else ""
    return f"{len(examples)} {label}: {preview}{suffix}."

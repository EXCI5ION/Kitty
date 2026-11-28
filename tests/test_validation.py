from __future__ import annotations

import csv
from pathlib import Path

from kitty.matrix_io import load_matrix, prepare_matrix
from kitty.project import ProjectState
from kitty.validation import validate_project


def _project(tmp_path: Path, rows: list[list[str]]) -> ProjectState:
    path = tmp_path / "matrix.csv"
    with path.open("w", encoding="utf-8", newline="") as stream:
        csv.writer(stream).writerows(rows)
    source = load_matrix(path)
    matrix = prepare_matrix(
        source,
        transposed=False,
        header_row=1,
        identifier_column=1,
        last_sample_row=len(rows),
        last_variable_column=len(rows[0]),
    )
    return ProjectState.from_prepared(matrix)


def test_valid_dataset_preserves_zeros_and_reports_constant_variables(
    tmp_path: Path,
) -> None:
    project = _project(
        tmp_path,
        [
            ["Muestra", "Variable", "Constante"],
            ["A1", "0", "5"],
            ["A2", "2", "5"],
            ["B1", "3", "5"],
            ["B2", "4", "5"],
        ],
    )
    for sample, class_name in zip(project.samples, ("A", "A", "B", "B")):
        sample.class_name = class_name

    report = validate_project(project)

    assert report.is_valid
    assert report.dataset is not None
    assert report.dataset.values[0][0] == 0.0
    assert report.zero_count == 1
    assert report.constant_variables == ("Constante",)
    assert {issue.code for issue in report.warnings} == {"constant_variables"}


def test_invalid_numeric_cells_prevent_numeric_dataset(tmp_path: Path) -> None:
    project = _project(
        tmp_path,
        [
            ["Muestra", "A", "B"],
            ["A1", "texto", "1"],
            ["A2", "2", ""],
            ["B1", "3", "4"],
            ["B2", "5", "inf"],
        ],
    )
    for sample, class_name in zip(project.samples, ("A", "A", "B", "B")):
        sample.class_name = class_name

    report = validate_project(project)

    assert not report.is_valid
    assert report.dataset is None
    assert {issue.code for issue in report.errors} == {
        "blank_cells",
        "nonfinite_cells",
        "nonnumeric_cells",
    }


def test_excluded_cells_are_not_validated(tmp_path: Path) -> None:
    project = _project(
        tmp_path,
        [
            ["Muestra", "A", "Excluir"],
            ["A1", "1", "texto"],
            ["A2", "2", "texto"],
            ["B1", "3", "texto"],
            ["B2", "4", "texto"],
            ["Fuera", "también texto", "texto"],
        ],
    )
    for sample, class_name in zip(project.samples[:4], ("A", "A", "B", "B")):
        sample.class_name = class_name
    project.samples[4].included = False
    project.variables[1].included = False

    report = validate_project(project)

    assert report.is_valid
    assert report.dataset is not None
    assert report.dataset.sample_names == ("A1", "A2", "B1", "B2")
    assert report.dataset.variable_names == ("A",)


def test_unclassified_samples_are_reported(tmp_path: Path) -> None:
    project = _project(
        tmp_path,
        [
            ["Muestra", "A"],
            ["A1", "1"],
            ["A2", "2"],
            ["B1", "3"],
            ["B2", "4"],
        ],
    )
    project.samples[0].class_name = "A"
    project.samples[1].class_name = "A"
    project.samples[2].class_name = "B"

    report = validate_project(project)

    assert not report.is_valid
    assert "unclassified_samples" in {issue.code for issue in report.errors}

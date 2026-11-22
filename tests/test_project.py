from __future__ import annotations

import csv
from pathlib import Path

from kitty.matrix_io import load_matrix, prepare_matrix
from kitty.project import ProjectState


def _project(tmp_path: Path) -> ProjectState:
    path = tmp_path / "matrix.csv"
    with path.open("w", encoding="utf-8", newline="") as stream:
        csv.writer(stream).writerows(
            [
                ["Muestra", "A", "B"],
                ["S1", "1", "2"],
                ["S2", "3", "4"],
                ["S3", "5", "6"],
            ]
        )
    source = load_matrix(path)
    matrix = prepare_matrix(
        source,
        transposed=False,
        header_row=1,
        identifier_column=1,
        last_sample_row=4,
        last_variable_column=3,
    )
    return ProjectState.from_prepared(matrix)


def test_class_counts_use_only_included_named_samples(tmp_path: Path) -> None:
    project = _project(tmp_path)
    project.samples[0].class_name = "Control"
    project.samples[1].class_name = "Tratado"
    project.samples[2].class_name = "Control"
    project.samples[2].included = False

    assert project.class_counts() == {"Control": 1, "Tratado": 1}


def test_metadata_survives_repreparing_same_region(tmp_path: Path) -> None:
    project = _project(tmp_path)
    project.samples[0].display_name = "Control 1"
    project.samples[0].class_name = "Control"
    project.variables[1].display_name = "Metabolito B"
    project.variables[1].included = False

    restored = ProjectState.from_prepared(project.matrix, project)

    assert restored.samples[0].display_name == "Control 1"
    assert restored.samples[0].class_name == "Control"
    assert restored.variables[1].display_name == "Metabolito B"
    assert restored.variables[1].included is False

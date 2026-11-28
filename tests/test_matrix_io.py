from __future__ import annotations

import csv
from pathlib import Path

import pytest

from kitty.matrix_io import MatrixImportError, load_matrix, prepare_matrix


def write_csv(path: Path, rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        csv.writer(stream).writerows(rows)


def test_csv_preserves_quoted_commas_and_multiline_headers(tmp_path: Path) -> None:
    path = tmp_path / "matrix.csv"
    write_csv(
        path,
        [
            ["Sample", "2,6-Dimethyldecane", "Header\ncontinued"],
            ["A1", "1.5", "2.5"],
            ["A2", "3.5", "4.5"],
        ],
    )

    source = load_matrix(path)

    assert source.rows[0] == ("Sample", "2,6-Dimethyldecane", "Header\ncontinued")
    assert source.row_count == 3
    assert source.column_count == 3


def test_prepare_matrix_uses_only_user_selected_region(tmp_path: Path) -> None:
    path = tmp_path / "matrix.csv"
    write_csv(
        path,
        [
            ["Sample", "A", "B"],
            ["S1", "1", "2"],
            ["S2", "3", "4"],
            ["Mean", "2", "3"],
        ],
    )
    source = load_matrix(path)

    prepared = prepare_matrix(
        source,
        transposed=False,
        header_row=1,
        identifier_column=1,
        last_sample_row=3,
        last_variable_column=3,
    )

    assert [sample.original_name for sample in prepared.samples] == ["S1", "S2"]
    assert [variable.original_name for variable in prepared.variables] == ["A", "B"]
    assert prepared.values == (("1", "2"), ("3", "4"))


def test_prepare_matrix_transposes_only_after_explicit_choice(tmp_path: Path) -> None:
    path = tmp_path / "matrix.csv"
    write_csv(
        path,
        [
            ["Variable", "S1", "S2"],
            ["A", "1", "3"],
            ["B", "2", "4"],
        ],
    )
    source = load_matrix(path)

    prepared = prepare_matrix(
        source,
        transposed=True,
        header_row=1,
        identifier_column=1,
        last_sample_row=3,
        last_variable_column=3,
    )

    assert [sample.original_name for sample in prepared.samples] == ["S1", "S2"]
    assert [variable.original_name for variable in prepared.variables] == ["A", "B"]
    assert prepared.values == (("1", "2"), ("3", "4"))


def test_invalid_region_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "matrix.csv"
    write_csv(path, [["Sample", "A"], ["S1", "1"]])
    source = load_matrix(path)

    with pytest.raises(MatrixImportError):
        prepare_matrix(
            source,
            transposed=False,
            header_row=1,
            identifier_column=1,
            last_sample_row=1,
            last_variable_column=2,
        )


def test_tab_delimited_txt_is_supported(tmp_path: Path) -> None:
    path = tmp_path / "matrix.txt"
    path.write_text("Muestra\tA\tB\nS1\t1\t2\n", encoding="utf-8")

    source = load_matrix(path)

    assert source.delimiter == "\t"
    assert source.rows == (("Muestra", "A", "B"), ("S1", "1", "2"))


@pytest.mark.parametrize("suffix", [".xlsx", ".ods", ".tsv"])
def test_spreadsheet_and_tsv_extensions_are_rejected(
    tmp_path: Path,
    suffix: str,
) -> None:
    path = tmp_path / f"matrix{suffix}"
    path.write_text("Muestra,A\nS1,1\n", encoding="utf-8")

    with pytest.raises(MatrixImportError, match="Formato no compatible"):
        load_matrix(path)


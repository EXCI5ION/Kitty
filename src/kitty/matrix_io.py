from __future__ import annotations

import csv
import io
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


SUPPORTED_EXTENSIONS = {".csv", ".txt"}


class MatrixImportError(ValueError):
    """Raised when a source cannot be represented as a rectangular matrix."""


@dataclass(frozen=True)
class MatrixSource:
    path: Path
    rows: tuple[tuple[str, ...], ...]
    delimiter: str | None = None

    @property
    def row_count(self) -> int:
        return len(self.rows)

    @property
    def column_count(self) -> int:
        return len(self.rows[0]) if self.rows else 0

    def transposed_rows(self) -> tuple[tuple[str, ...], ...]:
        return tuple(tuple(row[column] for row in self.rows) for column in range(self.column_count))


@dataclass(frozen=True)
class SampleDefinition:
    internal_id: str
    original_name: str
    display_name: str
    class_name: str = ""
    included: bool = True


@dataclass(frozen=True)
class VariableDefinition:
    internal_id: str
    original_name: str
    display_name: str
    included: bool = True


@dataclass(frozen=True)
class PreparedMatrix:
    source: MatrixSource
    transposed: bool
    header_row: int
    identifier_column: int
    last_sample_row: int
    last_variable_column: int
    samples: tuple[SampleDefinition, ...]
    variables: tuple[VariableDefinition, ...]
    values: tuple[tuple[str, ...], ...]

    def diagnostics(self) -> dict[str, int]:
        blanks = 0
        nonnumeric = 0
        nonfinite = 0
        negatives = 0
        zeros = 0
        for row in self.values:
            for raw_value in row:
                value = raw_value.strip()
                if not value:
                    blanks += 1
                    continue
                try:
                    numeric = float(value)
                except ValueError:
                    nonnumeric += 1
                    continue
                if not math.isfinite(numeric):
                    nonfinite += 1
                elif numeric < 0:
                    negatives += 1
                elif numeric == 0:
                    zeros += 1
        return {
            "blanks": blanks,
            "nonnumeric": nonnumeric,
            "nonfinite": nonfinite,
            "negatives": negatives,
            "zeros": zeros,
            "duplicate_sample_names": _duplicate_count(
                sample.original_name for sample in self.samples
            ),
            "duplicate_variable_names": _duplicate_count(
                variable.original_name for variable in self.variables
            ),
        }


def load_matrix(path: str | Path) -> MatrixSource:
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    suffix = source.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise MatrixImportError(f"Formato no compatible: {suffix or 'sin extensión'}")

    rows, delimiter = _read_delimited(source)

    rectangular = _rectangularize(rows)
    if len(rectangular) < 2 or len(rectangular[0]) < 2:
        raise MatrixImportError("La fuente debe contener al menos dos filas y dos columnas.")
    return MatrixSource(
        path=source.resolve(),
        rows=rectangular,
        delimiter=delimiter,
    )


def prepare_matrix(
    source: MatrixSource,
    *,
    transposed: bool,
    header_row: int,
    identifier_column: int,
    last_sample_row: int,
    last_variable_column: int,
) -> PreparedMatrix:
    rows = source.transposed_rows() if transposed else source.rows
    if not rows:
        raise MatrixImportError("La matriz está vacía.")
    row_count = len(rows)
    column_count = len(rows[0])
    if not 1 <= header_row < last_sample_row <= row_count:
        raise MatrixImportError("El intervalo de filas no es válido.")
    if not 1 <= identifier_column < last_variable_column <= column_count:
        raise MatrixImportError("El intervalo de columnas no es válido.")

    header_index = header_row - 1
    identifier_index = identifier_column - 1
    sample_rows = rows[header_row:last_sample_row]
    variable_columns = range(identifier_column, last_variable_column)

    samples = tuple(
        SampleDefinition(
            internal_id=f"sample_{index:04d}",
            original_name=row[identifier_index].strip(),
            display_name=row[identifier_index].strip(),
        )
        for index, row in enumerate(sample_rows, start=1)
    )
    variables = tuple(
        VariableDefinition(
            internal_id=f"variable_{index:04d}",
            original_name=rows[header_index][column].strip(),
            display_name=rows[header_index][column].strip(),
        )
        for index, column in enumerate(variable_columns, start=1)
    )
    values = tuple(
        tuple(row[column] for column in variable_columns) for row in sample_rows
    )
    return PreparedMatrix(
        source=source,
        transposed=transposed,
        header_row=header_row,
        identifier_column=identifier_column,
        last_sample_row=last_sample_row,
        last_variable_column=last_variable_column,
        samples=samples,
        variables=variables,
        values=values,
    )


def _read_delimited(path: Path) -> tuple[list[list[str]], str]:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as error:
        raise MatrixImportError(
            "El archivo no está codificado como UTF-8. Conviértalo a UTF-8 antes de importarlo."
        ) from error
    if not text.strip():
        raise MatrixImportError("El archivo está vacío.")
    delimiter = "\t" if path.suffix.lower() == ".txt" else ","
    try:
        delimiter = csv.Sniffer().sniff(text[:65536], delimiters=",;\t").delimiter
    except csv.Error:
        pass
    try:
        rows = [list(row) for row in csv.reader(io.StringIO(text), delimiter=delimiter)]
    except csv.Error as error:
        raise MatrixImportError(f"El archivo delimitado no es válido: {error}") from error
    return rows, delimiter


def _rectangularize(rows: Iterable[Iterable[object]]) -> tuple[tuple[str, ...], ...]:
    normalized = [[_cell_text(value) for value in row] for row in rows]
    while normalized and not any(cell for cell in normalized[-1]):
        normalized.pop()
    if not normalized:
        raise MatrixImportError("La fuente está vacía.")
    width = max(len(row) for row in normalized)
    while width and not any(len(row) >= width and row[width - 1] for row in normalized):
        width -= 1
    if width == 0:
        raise MatrixImportError("La fuente no contiene valores.")
    return tuple(tuple((row + [""] * width)[:width]) for row in normalized)


def _cell_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _duplicate_count(values: Iterable[str]) -> int:
    seen: set[str] = set()
    duplicates = 0
    for value in values:
        normalized = value.strip()
        if normalized in seen:
            duplicates += 1
        else:
            seen.add(normalized)
    return duplicates


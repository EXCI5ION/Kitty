from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QTableWidget,
)

from kitty.matrix_io import MatrixSource


class MatrixPreviewModel(QAbstractTableModel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.source: MatrixSource | None = None
        self.transposed = False
        self.header_row = 1
        self.identifier_column = 1
        self.last_sample_row = 1
        self.last_variable_column = 1
        self.theme = "light"

    def set_theme(self, theme: str) -> None:
        self.theme = theme if theme in {"dark", "crt"} else "light"
        if self.rowCount() and self.columnCount():
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(self.rowCount() - 1, self.columnCount() - 1),
                [Qt.BackgroundRole, Qt.ForegroundRole],
            )

    def set_source(self, source: MatrixSource, *, transposed: bool = False) -> None:
        self.beginResetModel()
        self.source = source
        self.transposed = transposed
        self.header_row = 1
        self.identifier_column = 1
        self.last_sample_row = self.rowCount()
        self.last_variable_column = self.columnCount()
        self.endResetModel()

    def set_region(
        self,
        *,
        header_row: int,
        identifier_column: int,
        last_sample_row: int,
        last_variable_column: int,
    ) -> None:
        self.header_row = header_row
        self.identifier_column = identifier_column
        self.last_sample_row = last_sample_row
        self.last_variable_column = last_variable_column
        if self.rowCount() and self.columnCount():
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(self.rowCount() - 1, self.columnCount() - 1),
                [Qt.BackgroundRole, Qt.ForegroundRole],
            )

    def rowCount(self, _parent: QModelIndex = QModelIndex()) -> int:
        if self.source is None:
            return 0
        return self.source.column_count if self.transposed else self.source.row_count

    def columnCount(self, _parent: QModelIndex = QModelIndex()) -> int:
        if self.source is None:
            return 0
        return self.source.row_count if self.transposed else self.source.column_count

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid() or self.source is None:
            return None
        row_number = index.row() + 1
        column_number = index.column() + 1
        if role == Qt.DisplayRole:
            source_row = index.column() if self.transposed else index.row()
            source_column = index.row() if self.transposed else index.column()
            return self.source.rows[source_row][source_column]
        if role == Qt.BackgroundRole:
            if self.theme == "crt":
                header_color = "#0d3b20"
                identifier_color = "#123322"
                data_color = "#09140d"
                outside_color = "#050b07"
            elif self.theme == "dark":
                header_color = "#174f52"
                identifier_color = "#3b354d"
                data_color = "#293138"
                outside_color = "#20262b"
            else:
                header_color = "#d8eceb"
                identifier_color = "#e8e0f3"
                data_color = "#f8fbfb"
                outside_color = "#eeeeee"
            if row_number == self.header_row and (
                self.identifier_column <= column_number <= self.last_variable_column
            ):
                return QColor(header_color)
            if column_number == self.identifier_column and (
                self.header_row <= row_number <= self.last_sample_row
            ):
                return QColor(identifier_color)
            inside = (
                self.header_row < row_number <= self.last_sample_row
                and self.identifier_column < column_number <= self.last_variable_column
            )
            if inside:
                return QColor(data_color)
            return QColor(outside_color)
        if role == Qt.ForegroundRole:
            if self.theme == "crt":
                return QColor("#8cff9a")
            if self.theme == "dark":
                return QColor("#e7ecef")
            inside_rows = self.header_row <= row_number <= self.last_sample_row
            inside_columns = self.identifier_column <= column_number <= self.last_variable_column
            if not (inside_rows and inside_columns):
                return QColor("#8a949b")
        return None

    def headerData(
        self,
        section: int,
        _orientation: Qt.Orientation,
        role: int = Qt.DisplayRole,
    ):
        if role == Qt.DisplayRole:
            return str(section + 1)
        return None


class EditableMetadataTable(QTableWidget):
    def __init__(self, editable_from_column: int, parent=None) -> None:
        super().__init__(parent)
        self.editable_from_column = editable_from_column
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.verticalHeader().setVisible(False)
        self.setAlternatingRowColors(True)

    def keyPressEvent(self, event) -> None:
        if event.matches(QKeySequence.StandardKey.Paste):
            self._paste_tabular()
            return
        if event.key() == Qt.Key_Space:
            rows = sorted({index.row() for index in self.selectedIndexes()})
            if rows and self.item(rows[0], 0) is not None:
                state = (
                    Qt.Unchecked
                    if self.item(rows[0], 0).checkState() == Qt.Checked
                    else Qt.Checked
                )
                for row in rows:
                    self.item(row, 0).setCheckState(state)
                return
        super().keyPressEvent(event)

    def mousePressEvent(self, event) -> None:
        index = self.indexAt(event.position().toPoint())
        if index.isValid() and index.column() == 0:
            rows = sorted({item.row() for item in self.selectedIndexes()})
            if index.row() not in rows:
                self.clearSelection()
                self.selectRow(index.row())
                rows = [index.row()]
            state = (
                Qt.Unchecked
                if self.item(index.row(), 0).checkState() == Qt.Checked
                else Qt.Checked
            )
            for row in rows:
                self.item(row, 0).setCheckState(state)
            event.accept()
            return
        super().mousePressEvent(event)

    def _paste_tabular(self) -> None:
        selected = self.selectedIndexes()
        if not selected:
            return
        start_row = min(index.row() for index in selected)
        start_column = max(
            self.editable_from_column,
            min(index.column() for index in selected),
        )
        clipboard_rows = [
            line.split("\t") for line in QApplication.clipboard().text().splitlines()
        ]
        for row_offset, values in enumerate(clipboard_rows):
            target_row = start_row + row_offset
            if target_row >= self.rowCount():
                break
            for column_offset, value in enumerate(values):
                target_column = start_column + column_offset
                if target_column >= self.columnCount():
                    break
                item = self.item(target_row, target_column)
                if item is not None and item.flags() & Qt.ItemIsEditable:
                    item.setText(value.strip())


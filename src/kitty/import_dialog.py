from __future__ import annotations

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from kitty.matrix_io import MatrixImportError, MatrixSource, PreparedMatrix, prepare_matrix
from kitty.project import ProjectState
from kitty.widgets import EditableMetadataTable, MatrixPreviewModel


class MatrixSetupDialog(QDialog):
    def __init__(
        self,
        source: MatrixSource,
        current: ProjectState | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.source = source
        self.current = current
        self.prepared: PreparedMatrix | None = None
        self.result_state: ProjectState | None = None
        self.transposed = current.matrix.transposed if current is not None else False
        self.setWindowTitle("Tabla")
        self.resize(1120, 720)
        self.setMinimumSize(820, 540)
        self._build_ui()
        self._set_source()
        if current is not None:
            self._restore_current(current)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)

        matrix_page = QWidget()
        matrix_layout = QVBoxLayout(matrix_page)
        matrix_layout.setContentsMargins(0, 8, 0, 0)
        toolbar = QHBoxLayout()
        self.transpose_button = QPushButton("Trasponer")
        self.transpose_button.clicked.connect(self.toggle_transpose)
        self.prepare_button = QPushButton("Preparar")
        self.prepare_button.setObjectName("primaryButton")
        self.prepare_button.clicked.connect(self.prepare_selection)
        self.source_label = QLabel()
        self.source_label.setObjectName("muted")
        toolbar.addWidget(self.transpose_button)
        toolbar.addWidget(self.prepare_button)
        toolbar.addStretch()
        toolbar.addWidget(self.source_label)
        matrix_layout.addLayout(toolbar)

        hint = QLabel(
            "Clic derecho sobre una celda para definir encabezados, muestras y variables."
        )
        hint.setObjectName("muted")
        matrix_layout.addWidget(hint)

        self.preview_model = MatrixPreviewModel(self)
        self.preview_model.set_theme(
            getattr(self.parent(), "current_theme", "light")
        )
        self.preview = QTableView()
        self.preview.setModel(self.preview_model)
        self.preview.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.preview.setAlternatingRowColors(False)
        self.preview.setSelectionMode(QAbstractItemView.SingleSelection)
        self.preview.horizontalHeader().setDefaultSectionSize(120)
        self.preview.verticalHeader().setDefaultSectionSize(25)
        self.preview.setContextMenuPolicy(Qt.CustomContextMenu)
        self.preview.customContextMenuRequested.connect(self.open_region_menu)
        matrix_layout.addWidget(self.preview, 1)

        self.region_summary = QLabel()
        self.region_summary.setObjectName("muted")
        matrix_layout.addWidget(self.region_summary)
        self.tabs.addTab(matrix_page, "Matriz")

        samples_page = QWidget()
        samples_layout = QVBoxLayout(samples_page)
        samples_layout.setContentsMargins(0, 8, 0, 0)
        samples_hint = QLabel("Edite únicamente el nombre que mostrará Kitty.")
        samples_hint.setObjectName("muted")
        samples_layout.addWidget(samples_hint)
        self.samples_table = QTableWidget(0, 3)
        self.samples_table.setHorizontalHeaderLabels(
            ["ID interno", "Identificador original", "Nombre mostrado"]
        )
        self.samples_table.verticalHeader().setVisible(False)
        self.samples_table.setAlternatingRowColors(True)
        self.samples_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.samples_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        samples_layout.addWidget(self.samples_table)
        self.tabs.addTab(samples_page, "Muestras")

        variables_page = QWidget()
        variables_layout = QVBoxLayout(variables_page)
        variables_layout.setContentsMargins(0, 8, 0, 0)
        variables_hint = QLabel(
            "Los encabezados originales se conservan aunque cambie el nombre mostrado."
        )
        variables_hint.setObjectName("muted")
        variables_layout.addWidget(variables_hint)
        self.variables_table = EditableMetadataTable(editable_from_column=3)
        self.variables_table.setColumnCount(4)
        self.variables_table.setHorizontalHeaderLabels(
            ["Incluir", "ID interno", "Encabezado original", "Nombre mostrado"]
        )
        self.variables_table.setColumnWidth(0, 64)
        self.variables_table.setColumnWidth(1, 110)
        self.variables_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.variables_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        variables_layout.addWidget(self.variables_table)
        self.tabs.addTab(variables_page, "Variables")

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        self.buttons.button(QDialogButtonBox.Save).setText("Aplicar")
        self.buttons.button(QDialogButtonBox.Save).setEnabled(False)
        self.buttons.accepted.connect(self.accept_configuration)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def _set_source(self) -> None:
        self.preview_model.set_source(self.source, transposed=self.transposed)
        self._reset_region()
        self.source_label.setText(self.source.path.name)

    def _reset_region(self) -> None:
        self.header_row = 1
        self.identifier_column = 1
        self.last_sample_row = self.preview_model.rowCount()
        self.last_variable_column = self.preview_model.columnCount()
        self._update_region()

    def _restore_current(self, current: ProjectState) -> None:
        matrix = current.matrix
        self.header_row = matrix.header_row
        self.identifier_column = matrix.identifier_column
        self.last_sample_row = matrix.last_sample_row
        self.last_variable_column = matrix.last_variable_column
        self.prepared = matrix
        self._update_region()
        self._populate_tables(current)
        self.buttons.button(QDialogButtonBox.Save).setEnabled(True)

    def toggle_transpose(self) -> None:
        self.transposed = not self.transposed
        self.preview_model.set_source(self.source, transposed=self.transposed)
        self._reset_region()
        self.prepared = None
        self.samples_table.setRowCount(0)
        self.variables_table.setRowCount(0)
        self.buttons.button(QDialogButtonBox.Save).setEnabled(False)

    def open_region_menu(self, position: QPoint) -> None:
        index = self.preview.indexAt(position)
        if not index.isValid():
            return
        row = index.row() + 1
        column = index.column() + 1
        menu = QMenu(self)
        header_action = menu.addAction(f"Fila {row} como encabezados")
        last_sample_action = menu.addAction(f"Fila {row} como última muestra")
        menu.addSeparator()
        identifier_action = menu.addAction(f"Columna {column} para muestras")
        last_variable_action = menu.addAction(f"Columna {column} como última variable")
        selected = menu.exec(self.preview.viewport().mapToGlobal(position))
        if selected == header_action:
            self.header_row = min(row, self.last_sample_row - 1)
        elif selected == last_sample_action:
            self.last_sample_row = max(row, self.header_row + 1)
        elif selected == identifier_action:
            self.identifier_column = min(column, self.last_variable_column - 1)
        elif selected == last_variable_action:
            self.last_variable_column = max(column, self.identifier_column + 1)
        else:
            return
        self.prepared = None
        self.buttons.button(QDialogButtonBox.Save).setEnabled(False)
        self._update_region()

    def _update_region(self) -> None:
        self.preview_model.set_region(
            header_row=self.header_row,
            identifier_column=self.identifier_column,
            last_sample_row=self.last_sample_row,
            last_variable_column=self.last_variable_column,
        )
        samples = self.last_sample_row - self.header_row
        variables = self.last_variable_column - self.identifier_column
        self.region_summary.setText(
            f"{samples:,} muestras × {variables:,} variables"
        )

    def prepare_selection(self) -> None:
        try:
            prepared = prepare_matrix(
                self.source,
                transposed=self.transposed,
                header_row=self.header_row,
                identifier_column=self.identifier_column,
                last_sample_row=self.last_sample_row,
                last_variable_column=self.last_variable_column,
            )
        except MatrixImportError as error:
            QMessageBox.warning(self, "Tabla", str(error))
            return
        self.prepared = prepared
        state = ProjectState.from_prepared(prepared, self.current)
        self._populate_tables(state)
        self.buttons.button(QDialogButtonBox.Save).setEnabled(True)
        self.tabs.setCurrentIndex(1)

    def _populate_tables(self, state: ProjectState) -> None:
        self.samples_table.setRowCount(len(state.samples))
        for row, sample in enumerate(state.samples):
            self.samples_table.setItem(row, 0, _readonly_item(sample.internal_id))
            self.samples_table.setItem(row, 1, _readonly_item(sample.original_name))
            self.samples_table.setItem(row, 2, QTableWidgetItem(sample.display_name))

        self.variables_table.setRowCount(len(state.variables))
        for row, variable in enumerate(state.variables):
            self.variables_table.setItem(row, 0, _check_item(variable.included))
            self.variables_table.setItem(row, 1, _readonly_item(variable.internal_id))
            self.variables_table.setItem(row, 2, _readonly_item(variable.original_name))
            self.variables_table.setItem(row, 3, QTableWidgetItem(variable.display_name))

    def accept_configuration(self) -> None:
        if self.prepared is None:
            return
        state = ProjectState.from_prepared(self.prepared, self.current)
        sample_names: list[str] = []
        for row, sample in enumerate(state.samples):
            display_name = self.samples_table.item(row, 2).text().strip()
            sample.display_name = display_name
            sample_names.append(display_name)
        if any(not name for name in sample_names):
            QMessageBox.warning(self, "Tabla", "Hay muestras sin nombre.")
            return
        if len(set(sample_names)) != len(sample_names):
            QMessageBox.warning(self, "Tabla", "Los nombres de muestra deben ser únicos.")
            return

        included_variables = 0
        for row, variable in enumerate(state.variables):
            variable.included = (
                self.variables_table.item(row, 0).checkState() == Qt.Checked
            )
            variable.display_name = self.variables_table.item(row, 3).text().strip()
            if variable.included:
                included_variables += 1
                if not variable.display_name:
                    QMessageBox.warning(
                        self,
                        "Tabla",
                        "Hay variables incluidas sin nombre.",
                    )
                    return
        if not included_variables:
            QMessageBox.warning(self, "Tabla", "Incluya al menos una variable.")
            return
        self.result_state = state
        self.accept()


def _readonly_item(text: str) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
    return item


def _check_item(checked: bool) -> QTableWidgetItem:
    item = QTableWidgetItem()
    item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable)
    item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
    item.setTextAlignment(Qt.AlignCenter)
    return item


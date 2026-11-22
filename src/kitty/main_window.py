from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QKeySequence,
    QPalette,
    QUndoStack,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStyleFactory,
    QTabWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from kitty import __version__
from kitty.import_dialog import MatrixSetupDialog
from kitty.matrix_io import (
    MatrixImportError,
    list_sheet_names,
    load_matrix,
    prepare_matrix,
)
from kitty.project import ProjectState
from kitty.widgets import EditableMetadataTable


class ContrastDialog(QDialog):
    def __init__(
        self,
        classes: list[str],
        current: tuple[str, str] | None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Contraste")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.reference = QComboBox()
        self.comparison = QComboBox()
        self.reference.addItems(classes)
        self.comparison.addItems(classes)
        if current is not None:
            self.reference.setCurrentText(current[0])
            self.comparison.setCurrentText(current[1])
        elif len(classes) > 1:
            self.comparison.setCurrentIndex(1)
        form.addRow("Referencia", self.reference)
        form.addRow("Comparación", self.comparison)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept_if_valid)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _accept_if_valid(self) -> None:
        if self.reference.currentText() == self.comparison.currentText():
            QMessageBox.warning(self, "Contraste", "Seleccione dos clases diferentes.")
            return
        self.accept()

    def result_pair(self) -> tuple[str, str]:
        return self.reference.currentText(), self.comparison.currentText()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.settings = QSettings("Kitty", "Kitty")
        self.project: ProjectState | None = None
        self.direct_contrast: tuple[str, str] | None = None
        self._loading = False
        self.undo_stack = QUndoStack(self)
        application = QApplication.instance()
        self._system_style_name = (
            application.style().objectName() if application is not None else "Fusion"
        )
        self._system_palette = (
            QPalette(application.palette()) if application is not None else QPalette()
        )
        self.setWindowTitle("Kitty")
        self.resize(1280, 780)
        self.setMinimumSize(960, 620)
        self._build_ui()
        self._build_menus()
        self.apply_theme(self.settings.value("theme", "light", str))
        self._update_actions()

    def _build_ui(self) -> None:
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        self.setCentralWidget(splitter)

        left = QWidget()
        left.setMinimumWidth(300)
        left.setMaximumWidth(440)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(6, 6, 3, 6)
        left_layout.setSpacing(4)

        samples_label = QLabel("Muestras y clases")
        samples_label.setObjectName("sectionTitle")
        left_layout.addWidget(samples_label)
        self.sample_table = EditableMetadataTable(editable_from_column=2)
        self.sample_table.setColumnCount(4)
        self.sample_table.setHorizontalHeaderLabels(
            ["Incluir", "Muestra", "Clase", "Individuo"]
        )
        sample_header = self.sample_table.horizontalHeader()
        sample_header.setSectionResizeMode(QHeaderView.Interactive)
        self.sample_table.setColumnWidth(0, 56)
        self.sample_table.setColumnWidth(1, 130)
        self.sample_table.setColumnWidth(2, 100)
        self.sample_table.setColumnWidth(3, 100)
        self.sample_table.itemChanged.connect(self._sample_changed)
        left_layout.addWidget(self.sample_table, 1)

        controls = QFrame()
        controls.setObjectName("controlPanel")
        controls_layout = QVBoxLayout(controls)
        controls_layout.setContentsMargins(4, 6, 4, 4)
        controls_layout.setSpacing(6)
        self.assign_class_button = QPushButton("Asignar clase")
        self.assign_class_button.clicked.connect(self.assign_class)
        controls_layout.addWidget(self.assign_class_button)

        self.multiple_comparison = QCheckBox("Comparación múltiple")
        self.multiple_comparison.setChecked(True)
        controls_layout.addWidget(self.multiple_comparison)

        posthoc_row = QHBoxLayout()
        posthoc_row.addWidget(QLabel("Post hoc"))
        self.posthoc = QComboBox()
        self.posthoc.addItem("Tukey HSD", "tukey")
        self.posthoc.addItem("Games–Howell", "games_howell")
        self.posthoc.addItem("Dunn", "dunn")
        posthoc_row.addWidget(self.posthoc, 1)
        controls_layout.addLayout(posthoc_row)
        self.multiple_comparison.toggled.connect(self.posthoc.setEnabled)

        contrast_row = QHBoxLayout()
        self.contrast_button = QPushButton("Contrastes…")
        self.contrast_button.clicked.connect(self.configure_contrast)
        self.contrast_label = QLabel("Sin definir")
        self.contrast_label.setObjectName("muted")
        self.contrast_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        contrast_row.addWidget(self.contrast_button)
        contrast_row.addWidget(self.contrast_label, 1)
        controls_layout.addLayout(contrast_row)

        self.execute_button = QPushButton("Ejecutar")
        self.execute_button.setObjectName("primaryButton")
        self.execute_button.clicked.connect(self.execute_analysis)
        controls_layout.addWidget(self.execute_button)
        left_layout.addWidget(controls)
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(3, 6, 6, 6)
        self.results_tabs = QTabWidget()
        self.results_tabs.setDocumentMode(True)
        self.summary_label = QLabel()
        self.summary_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.summary_label.setWordWrap(True)
        self.summary_label.setMargin(16)
        summary_page = QWidget()
        summary_layout = QVBoxLayout(summary_page)
        summary_layout.setContentsMargins(0, 0, 0, 0)
        summary_layout.addWidget(self.summary_label)
        self.results_tabs.addTab(summary_page, "Resumen")
        self.heatmap_page = self._placeholder_page("Sin heatmap")
        self.foldchange_page = self._placeholder_page("Sin resultados")
        self.boxplot_page = self._placeholder_page("Sin boxplots")
        self.tables_page = self._placeholder_page("Sin tablas")
        self.results_tabs.addTab(self.heatmap_page, "Heatmap")
        self.results_tabs.addTab(self.foldchange_page, "Fold Change")
        self.results_tabs.addTab(self.boxplot_page, "Boxplot")
        self.results_tabs.addTab(self.tables_page, "Tablas")
        right_layout.addWidget(self.results_tabs)
        splitter.addWidget(right)
        splitter.setSizes([360, 920])
        self._update_summary()

    @staticmethod
    def _placeholder_page(text: str) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        label = QLabel(text)
        label.setObjectName("placeholder")
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)
        return page

    def _build_menus(self) -> None:
        file_menu = self.menuBar().addMenu("Archivo")
        self.load_action = QAction("Cargar…", self)
        self.load_action.setShortcut(QKeySequence.StandardKey.Open)
        self.load_action.triggered.connect(self.load_project_matrix)
        self.save_action = QAction("Guardar", self)
        self.save_action.setShortcut(QKeySequence.StandardKey.Save)
        self.save_action.setEnabled(False)
        self.save_as_action = QAction("Guardar como…", self)
        self.save_as_action.setShortcut(QKeySequence.StandardKey.SaveAs)
        self.save_as_action.setEnabled(False)
        self.export_action = QAction("Exportar…", self)
        self.export_action.setEnabled(False)
        exit_action = QAction("Salir", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(self.load_action)
        file_menu.addAction(self.save_action)
        file_menu.addAction(self.save_as_action)
        file_menu.addSeparator()
        file_menu.addAction(self.export_action)
        file_menu.addSeparator()
        file_menu.addAction(exit_action)

        edit_menu = self.menuBar().addMenu("Editar")
        edit_menu.addAction(self.undo_stack.createUndoAction(self, "Deshacer"))
        edit_menu.addAction(self.undo_stack.createRedoAction(self, "Rehacer"))
        edit_menu.addSeparator()
        self.table_action = QAction("Tabla…", self)
        self.table_action.triggered.connect(self.edit_table)
        self.transpose_action = QAction("Trasponer…", self)
        self.transpose_action.triggered.connect(
            lambda: self.edit_table(transpose_on_open=True)
        )
        edit_menu.addAction(self.table_action)
        edit_menu.addAction(self.transpose_action)

        view_menu = self.menuBar().addMenu("Ver")
        theme_menu = view_menu.addMenu("Tema")
        theme_group = QActionGroup(self)
        theme_group.setExclusive(True)
        current_theme = self.settings.value("theme", "light", str)
        if current_theme not in {"light", "dark", "classic", "crt"}:
            current_theme = "light"
        for label, value in (
            ("Claro", "light"),
            ("Oscuro", "dark"),
            ("Clásico", "classic"),
            ("CRT", "crt"),
        ):
            action = QAction(label, self, checkable=True)
            action.setData(value)
            action.setChecked(value == current_theme)
            action.triggered.connect(lambda _checked, name=value: self.apply_theme(name))
            theme_group.addAction(action)
            theme_menu.addAction(action)
        self.style_action = QAction("Estilo…", self)
        self.style_action.setEnabled(False)
        report_action = QAction("Informe", self)
        report_action.triggered.connect(lambda: self.results_tabs.setCurrentIndex(0))
        view_menu.addAction(self.style_action)
        view_menu.addAction(report_action)

        help_menu = self.menuBar().addMenu("Ayuda")
        manual_action = QAction("Manual", self)
        manual_action.setEnabled(False)
        documentation_action = QAction("Documentación", self)
        documentation_action.setEnabled(False)
        about_action = QAction("Acerca de Kitty", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(manual_action)
        help_menu.addAction(documentation_action)
        help_menu.addSeparator()
        help_menu.addAction(about_action)

    def load_project_matrix(self) -> None:
        source = self._choose_source()
        if source is None:
            return
        try:
            prepared = prepare_matrix(
                source,
                transposed=False,
                header_row=1,
                identifier_column=1,
                last_sample_row=source.row_count,
                last_variable_column=source.column_count,
            )
        except MatrixImportError as error:
            QMessageBox.critical(self, "Cargar", str(error))
            return
        self.project = ProjectState.from_prepared(prepared)
        self.direct_contrast = None
        self._clear_results()
        self._populate_samples()
        self._update_summary()
        self._update_actions()
        self.statusBar().showMessage("Matriz cargada")

    def _choose_source(self):
        start_directory = self.settings.value("last_directory", "", str)
        path, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Cargar matriz",
            start_directory,
            "Matrices (*.csv *.tsv *.txt *.xlsx *.ods);;Todos los archivos (*)",
        )
        if not path:
            return None
        self.settings.setValue("last_directory", str(Path(path).parent))
        try:
            sheets = list_sheet_names(path)
            sheet_name = None
            if sheets:
                sheet_name, accepted = QInputDialog.getItem(
                    self,
                    "Hoja",
                    "Seleccionar",
                    list(sheets),
                    0,
                    False,
                )
                if not accepted:
                    return None
            QApplication.setOverrideCursor(Qt.WaitCursor)
            return load_matrix(path, sheet_name)
        except (OSError, MatrixImportError) as error:
            QMessageBox.critical(self, "Cargar", str(error))
            return None
        finally:
            QApplication.restoreOverrideCursor()

    def edit_table(self, *, transpose_on_open: bool = False) -> None:
        if self.project is None:
            return
        dialog = MatrixSetupDialog(
            self.project.matrix.source,
            current=self.project,
            parent=self,
        )
        if transpose_on_open:
            dialog.toggle_transpose()
        if dialog.exec() != QDialog.Accepted or dialog.result_state is None:
            return
        self.project = dialog.result_state
        self._populate_samples()
        self._update_summary()
        self._update_actions()
        self.statusBar().showMessage("Tabla actualizada")

    def _populate_samples(self) -> None:
        if self.project is None:
            self.sample_table.setRowCount(0)
            return
        self._loading = True
        try:
            self.sample_table.setRowCount(len(self.project.samples))
            for row, sample in enumerate(self.project.samples):
                include = QTableWidgetItem()
                include.setFlags(
                    Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable
                )
                include.setCheckState(Qt.Checked if sample.included else Qt.Unchecked)
                include.setTextAlignment(Qt.AlignCenter)
                name = QTableWidgetItem(sample.display_name)
                name.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                self.sample_table.setItem(row, 0, include)
                self.sample_table.setItem(row, 1, name)
                self.sample_table.setItem(row, 2, QTableWidgetItem(sample.class_name))
                self.sample_table.setItem(row, 3, QTableWidgetItem(sample.individual))
        finally:
            self._loading = False

    def _sample_changed(self, item: QTableWidgetItem) -> None:
        if self._loading or self.project is None:
            return
        sample = self.project.samples[item.row()]
        if item.column() == 0:
            sample.included = item.checkState() == Qt.Checked
        elif item.column() == 2:
            sample.class_name = item.text().strip()
        elif item.column() == 3:
            sample.individual = item.text().strip()
        self._refresh_classes()
        self._update_summary()

    def assign_class(self) -> None:
        if self.project is None:
            return
        rows = sorted({index.row() for index in self.sample_table.selectedIndexes()})
        if not rows:
            QMessageBox.information(self, "Clase", "Seleccione una o más muestras.")
            return
        current = self.sample_table.item(rows[0], 2).text()
        value, accepted = QInputDialog.getText(
            self,
            "Clase",
            "Nombre",
            text=current,
        )
        if not accepted or not value.strip():
            return
        self._loading = True
        try:
            for row in rows:
                class_name = value.strip()
                self.sample_table.item(row, 2).setText(class_name)
                self.project.samples[row].class_name = class_name
        finally:
            self._loading = False
        self._refresh_classes()
        self._update_summary()

    def _refresh_classes(self) -> None:
        available = set(self.project.class_counts()) if self.project else set()
        if self.direct_contrast is not None and not set(self.direct_contrast) <= available:
            self.direct_contrast = None
            self.contrast_label.setText("Sin definir")
        self._update_actions()

    def configure_contrast(self) -> None:
        if self.project is None:
            return
        classes = list(self.project.class_counts())
        if len(classes) < 2:
            QMessageBox.information(self, "Contraste", "Asigne al menos dos clases.")
            return
        dialog = ContrastDialog(classes, self.direct_contrast, self)
        if dialog.exec() != QDialog.Accepted:
            return
        self.direct_contrast = dialog.result_pair()
        reference, comparison = self.direct_contrast
        self.contrast_label.setText(f"{comparison} / {reference}")
        self._update_summary()
        self._update_actions()

    def execute_analysis(self) -> None:
        if self.project is None:
            return
        QMessageBox.information(
            self,
            "Kitty",
            "La configuración quedó lista. El motor estadístico será el próximo módulo.",
        )

    def _update_actions(self) -> None:
        has_project = self.project is not None
        self.table_action.setEnabled(has_project)
        self.transpose_action.setEnabled(has_project)
        self.assign_class_button.setEnabled(has_project)
        class_count = len(self.project.class_counts()) if self.project else 0
        self.contrast_button.setEnabled(has_project and class_count >= 2)
        self.execute_button.setEnabled(has_project and class_count >= 2)

    def _update_summary(self) -> None:
        if self.project is None:
            self.summary_label.setText(
                "<h2>Kitty</h2><p>Cargue una matriz para comenzar.</p>"
            )
            return
        project = self.project
        matrix = project.matrix
        classes = project.class_counts()
        class_text = " · ".join(
            f"{name}: {count}" for name, count in classes.items()
        ) or "Sin clases asignadas"
        contrast = (
            f"{self.direct_contrast[1]} / {self.direct_contrast[0]}"
            if self.direct_contrast
            else "Sin definir"
        )
        orientation = "traspuesta" if matrix.transposed else "original"
        self.summary_label.setText(
            f"<h2>{matrix.source.path.name}</h2>"
            f"<p><b>Matriz</b><br>"
            f"{project.included_sample_count()} muestras incluidas · "
            f"{project.included_variable_count()} variables incluidas · "
            f"orientación {orientation}</p>"
            f"<p><b>Clases</b><br>{class_text}</p>"
            f"<p><b>Contraste</b><br>{contrast}</p>"
            f"<p><b>Comparación múltiple</b><br>Sin resultados</p>"
        )

    def _clear_results(self) -> None:
        for page, text in (
            (self.heatmap_page, "Sin heatmap"),
            (self.foldchange_page, "Sin resultados"),
            (self.boxplot_page, "Sin boxplots"),
            (self.tables_page, "Sin tablas"),
        ):
            label = page.findChild(QLabel, "placeholder")
            if label is not None:
                label.setText(text)
        self.results_tabs.setCurrentIndex(0)

    def show_about(self) -> None:
        QMessageBox.about(
            self,
            "Acerca de Kitty",
            f"<h3>Kitty {__version__}</h3>"
            "<p>Análisis estadístico univariado para matrices ómicas.</p>"
            "<p>Software libre bajo GPL-3.0-or-later.</p>",
        )

    def apply_theme(self, theme: str) -> None:
        if theme not in {"light", "dark", "classic", "crt"}:
            theme = "light"
        self.current_theme = theme
        self.settings.setValue("theme", theme)
        application = QApplication.instance()
        if application is not None:
            if theme == "classic":
                classic_style = QStyleFactory.create("Windows")
                if classic_style is not None:
                    application.setStyle(classic_style)
                application.setPalette(application.style().standardPalette())
            else:
                system_style = QStyleFactory.create(self._system_style_name)
                if system_style is not None:
                    application.setStyle(system_style)
                application.setPalette(QPalette(self._system_palette))
        if theme in {"light", "classic"}:
            self.setStyleSheet("")
            return
        if theme == "crt":
            colors = {
                "window": "#050b07",
                "panel": "#09140d",
                "text": "#8cff9a",
                "muted": "#4e9f64",
                "border": "#1f8a46",
                "header": "#0d3b20",
                "accent": "#39ff6a",
                "alternate": "#0c1c12",
                "selection": "#145c2d",
                "radius": "0px",
                "font": "font-family: Consolas, 'Courier New', monospace;",
            }
        else:
            colors = {
                "window": "#20262b",
                "panel": "#293138",
                "text": "#e7ecef",
                "muted": "#a9b5bc",
                "border": "#46525a",
                "header": "#174f52",
                "accent": "#1b8d90",
                "alternate": "#252d33",
                "selection": "#176f72",
                "radius": "4px",
                "font": "",
            }
        self.setStyleSheet(
            f"""
            QMainWindow, QWidget {{ background: {colors['window']}; color: {colors['text']}; {colors['font']} }}
            QMenuBar, QMenu, QStatusBar {{ background: {colors['panel']}; color: {colors['text']}; }}
            QMenuBar::item:selected, QMenu::item:selected {{ background: {colors['selection']}; color: {colors['text']}; }}
            QFrame#controlPanel {{ background: {colors['panel']}; border: 1px solid {colors['border']}; }}
            QLabel#sectionTitle {{ font-weight: 650; }}
            QLabel#muted {{ color: {colors['muted']}; }}
            QLabel#placeholder {{ color: {colors['muted']}; font-size: 14px; }}
            QTabWidget::pane {{ background: {colors['panel']}; border: 1px solid {colors['border']}; }}
            QTabBar::tab {{ padding: 7px 14px; background: {colors['window']}; }}
            QTabBar::tab:selected {{ background: {colors['panel']}; color: {colors['accent']}; font-weight: 600; }}
            QPushButton {{ background: {colors['panel']}; color: {colors['text']}; border: 1px solid {colors['border']}; border-radius: {colors['radius']}; padding: 6px 10px; }}
            QPushButton:hover {{ border-color: {colors['accent']}; }}
            QPushButton:disabled {{ color: {colors['muted']}; }}
            QPushButton#primaryButton {{ background: {colors['accent']}; color: {colors['window']}; border-color: {colors['accent']}; font-weight: 700; }}
            QTableView, QTableWidget, QTableView::viewport, QTableWidget::viewport, QComboBox {{ background: {colors['panel']}; color: {colors['text']}; border: 1px solid {colors['border']}; alternate-background-color: {colors['alternate']}; }}
            QTableView::item:selected, QTableWidget::item:selected {{ background: {colors['selection']}; color: {colors['text']}; }}
            QHeaderView::section {{ background: {colors['header']}; color: {colors['text']}; padding: 5px; border: 0; border-right: 1px solid {colors['border']}; }}
            QTableCornerButton::section {{ background: {colors['header']}; border: 0; border-right: 1px solid {colors['border']}; border-bottom: 1px solid {colors['border']}; }}
            QCheckBox {{ spacing: 7px; }}
            """
        )


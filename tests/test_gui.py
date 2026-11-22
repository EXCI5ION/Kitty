from __future__ import annotations

import os
import csv
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QHeaderView

from kitty.import_dialog import MatrixSetupDialog
from kitty.main_window import MainWindow
from kitty.matrix_io import load_matrix
from kitty.widgets import MatrixPreviewModel


@pytest.fixture(scope="module")
def application() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_main_window_matches_initial_workspace(application: QApplication) -> None:
    window = MainWindow()

    assert window.windowTitle() == "Kitty"
    assert [
        window.results_tabs.tabText(index)
        for index in range(window.results_tabs.count())
    ] == ["Resumen", "Heatmap", "Fold Change", "Boxplot", "Tablas"]
    assert [
        window.sample_table.horizontalHeaderItem(column).text()
        for column in range(window.sample_table.columnCount())
    ] == ["Incluir", "Muestra", "Clase", "Individuo"]
    assert window.multiple_comparison.isChecked()
    assert window.posthoc.currentData() == "tukey"
    assert window.execute_button.isEnabled() is False
    assert all(
        window.sample_table.horizontalHeader().sectionResizeMode(column)
        == QHeaderView.Interactive
        for column in range(window.sample_table.columnCount())
    )

    window.close()


def test_planned_menus_are_present(application: QApplication) -> None:
    window = MainWindow()

    assert [action.text() for action in window.menuBar().actions()] == [
        "Archivo",
        "Editar",
        "Ver",
        "Ayuda",
    ]
    view_menu = window.menuBar().actions()[2].menu()
    theme_menu = view_menu.actions()[0].menu()
    assert [action.text() for action in theme_menu.actions()] == [
        "Claro",
        "Oscuro",
        "Clásico",
        "CRT",
    ]

    window.close()


def test_matrix_dialog_prepares_and_applies_selection(
    application: QApplication,
    tmp_path: Path,
) -> None:
    path = tmp_path / "matrix.csv"
    with path.open("w", encoding="utf-8", newline="") as stream:
        csv.writer(stream).writerows(
            [
                ["Muestra", "A", "B"],
                ["S1", "1", "2"],
                ["S2", "3", "4"],
            ]
        )

    dialog = MatrixSetupDialog(load_matrix(path))
    dialog.prepare_selection()
    dialog.accept_configuration()

    assert dialog.result_state is not None
    assert len(dialog.result_state.samples) == 2
    assert len(dialog.result_state.variables) == 2
    assert dialog.result_state.matrix.values == (("1", "2"), ("3", "4"))


def test_loading_uses_default_region_without_opening_setup_dialog(
    application: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "direct.csv"
    with path.open("w", encoding="utf-8", newline="") as stream:
        csv.writer(stream).writerows(
            [
                ["Muestra", "A", "B"],
                ["S1", "1", "2"],
                ["S2", "3", "4"],
            ]
        )
    source = load_matrix(path)
    window = MainWindow()
    monkeypatch.setattr(window, "_choose_source", lambda: source)
    monkeypatch.setattr(
        MatrixSetupDialog,
        "exec",
        lambda _dialog: pytest.fail("No debe abrirse el diálogo de tabla al cargar"),
    )

    window.load_project_matrix()

    assert window.project is not None
    assert window.sample_table.rowCount() == 2
    assert [sample.display_name for sample in window.project.samples] == ["S1", "S2"]
    window.close()


def test_light_and_classic_themes_restore_native_appearance(
    application: QApplication,
) -> None:
    window = MainWindow()

    window.apply_theme("dark")
    assert window.styleSheet()
    window.apply_theme("light")
    assert window.styleSheet() == ""
    window.apply_theme("classic")
    assert window.styleSheet() == ""

    window.apply_theme("light")
    window.close()


def test_crt_theme_uses_terminal_palette(application: QApplication) -> None:
    window = MainWindow()

    window.apply_theme("crt")

    assert "#39ff6a" in window.styleSheet()
    assert "Consolas" in window.styleSheet()
    window.apply_theme("light")
    window.close()


def test_matrix_preview_uses_dark_cell_backgrounds(
    application: QApplication,
    tmp_path: Path,
) -> None:
    path = tmp_path / "preview.csv"
    with path.open("w", encoding="utf-8", newline="") as stream:
        csv.writer(stream).writerows([["Muestra", "A"], ["S1", "1"]])
    model = MatrixPreviewModel()
    model.set_source(load_matrix(path))

    model.set_theme("dark")
    assert model.data(model.index(1, 1), Qt.BackgroundRole).name() == "#293138"
    model.set_theme("crt")
    assert model.data(model.index(1, 1), Qt.BackgroundRole).name() == "#09140d"

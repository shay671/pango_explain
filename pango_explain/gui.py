"""Graphical interface for exploring Pango alias mappings.

This module exposes a small PyQt6-based utility that lets users enter a Pango
alias and view the corresponding lineage or lineages defined in the
``alias_key.json`` file shipped with the project.  The graphical code is
implemented lazily so importing :mod:`pango_explain.gui` only requires PyQt6
when the GUI is actually launched.
"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, MutableMapping, Optional, Sequence, Union

try:  # pragma: no cover - import fallback exercised only when run as a script
    from .pango_alias import (
        AliasValue,
        default_report_path,
        get_ancestral_dict,
        generate_alias_ancestry_report,
        load_alias_map,
        lookup_alias,
        unroll_pango_name,
        write_alias_ancestry_workbook,
    )
except ImportError:  # pragma: no cover - executed when ``__package__`` is empty
    # Allow ``python path/to/gui.py`` by temporarily adding the package root to
    # ``sys.path`` before importing.  This branch mirrors the logic commonly
    # recommended for modules that support both package and script execution.
    import sys

    package_root = Path(__file__).resolve().parent.parent
    if str(package_root) not in sys.path:
        sys.path.insert(0, str(package_root))

    from pango_explain.pango_alias import (
        AliasValue,
        default_report_path,
        get_ancestral_dict,
        generate_alias_ancestry_report,
        load_alias_map,
        lookup_alias,
        unroll_pango_name,
        write_alias_ancestry_workbook,
    )


DEFAULT_ALIAS_MAP_PATH = Path(__file__).resolve().parent.parent / "alias_key.json"


def _normalise_alias_map(
    alias_map: Optional[Mapping[str, AliasValue]],
    alias_map_path: Optional[Union[str, Path]],
) -> MutableMapping[str, AliasValue]:
    """Return a mutable alias mapping using ``alias_map`` or the provided path."""

    if alias_map is not None:
        # ``lookup_alias`` expects a mutable mapping, so make a shallow copy if
        # needed without mutating the caller's mapping.
        if isinstance(alias_map, MutableMapping):
            return alias_map
        return dict(alias_map)

    path = Path(alias_map_path) if alias_map_path is not None else DEFAULT_ALIAS_MAP_PATH
    return load_alias_map(path)


def _format_alias_value(value: AliasValue) -> str:
    """Return a human-readable representation of ``value`` for display."""

    if isinstance(value, str):
        return value or "(empty string)"
    if isinstance(value, Sequence):
        return "\n".join(value)
    return str(value)


def _format_ancestry(ancestry: Mapping[str, Optional[str]]) -> str:
    """Return a readable description for an ancestry mapping."""

    lines = []
    for alias, parent in ancestry.items():
        if parent:
            lines.append(f"{alias} = {parent}")
        else:
            lines.append(f"{alias}")
    return "\n".join(lines)


def unroll_aliance(
    alias: str,
    *,
    alias_map: Optional[Mapping[str, AliasValue]] = None,
    alias_map_path: Optional[Union[str, Path]] = None,
) -> Optional[AliasValue]:
    """Return the value stored for ``alias`` in the alias mapping.

    Parameters
    ----------
    alias:
        The alias string to look up.
    alias_map:
        Optional mapping to use instead of loading the alias file again.
    alias_map_path:
        Path to the alias map JSON file. Used only when ``alias_map`` is not
        supplied.
    """

    resolved_map = _normalise_alias_map(alias_map, alias_map_path)
    return lookup_alias(alias, resolved_map)


def run_gui(alias_map_path: Optional[Union[str, Path]] = None) -> None:
    """Launch the PyQt6 GUI for browsing the alias mapping."""

    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import (
        QApplication,
        QFileDialog,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMessageBox,
        QPushButton,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )

    class AliasLookupWindow(QMainWindow):
        """Main window for the alias lookup GUI."""

        def __init__(self, initial_path: Optional[Union[str, Path]] = None) -> None:
            super().__init__()

            self._current_path = Path(initial_path) if initial_path else DEFAULT_ALIAS_MAP_PATH
            try:
                self._alias_map = load_alias_map(self._current_path)
            except Exception as exc:  # pragma: no cover - GUI feedback path
                QMessageBox.critical(
                    self,
                    "Failed to load alias mapping",
                    f"Could not load alias mapping from {self._current_path}: {exc}",
                )
                self._alias_map = {}

            self.setWindowTitle("Pango Alias Explorer")
            self.resize(500, 400)

            central = QWidget()
            layout = QVBoxLayout(central)
            layout.setContentsMargins(12, 12, 12, 12)
            layout.setSpacing(8)

            description = QLabel(
                "Enter a Pango alias to unroll it into the full designation(s) "
                "or display its ancestry."
            )
            description.setWordWrap(True)
            layout.addWidget(description)

            self._alias_input = QLineEdit()
            self._alias_input.setPlaceholderText("e.g. BA")
            self._alias_input.returnPressed.connect(self._on_lookup)
            layout.addWidget(self._alias_input)

            button_row = QWidget()
            button_layout = QHBoxLayout(button_row)
            button_layout.setContentsMargins(0, 0, 0, 0)
            button_layout.setSpacing(6)

            lookup_button = QPushButton("Unroll alias")
            lookup_button.clicked.connect(self._on_lookup)
            button_layout.addWidget(lookup_button)

            check_button = QPushButton("Unroll Pango name")
            check_button.clicked.connect(self._on_check_pango_name)
            button_layout.addWidget(check_button)

            ancestry_button = QPushButton("Show ancestry")
            ancestry_button.clicked.connect(self._on_show_ancestry)
            button_layout.addWidget(ancestry_button)

            report_button = QPushButton("Save alias report")
            report_button.clicked.connect(self._on_save_alias_report)
            button_layout.addWidget(report_button)

            load_button = QPushButton("Load alias file…")
            load_button.clicked.connect(self._on_select_file)
            button_layout.addWidget(load_button)

            button_layout.addStretch()

            layout.addWidget(button_row)

            self._result = QTextEdit()
            self._result.setReadOnly(True)
            layout.addWidget(self._result)

            self._status = QLabel(self._status_text())
            self._status.setAlignment(Qt.AlignmentFlag.AlignLeft)
            layout.addWidget(self._status)

            self.setCentralWidget(central)

        def _status_text(self) -> str:
            count = len(self._alias_map)
            return f"Loaded {count} aliases from {self._current_path}"

        def _on_lookup(self) -> None:
            alias = self._alias_input.text().strip()
            if not alias:
                QMessageBox.information(self, "Alias required", "Please enter an alias to unroll.")
                return

            value = unroll_aliance(alias, alias_map=self._alias_map)
            if value is None:
                self._result.setPlainText(f"No mapping found for alias '{alias}'.")
            else:
                self._result.setPlainText(_format_alias_value(value))

        def _on_check_pango_name(self) -> None:
            designation = self._alias_input.text().strip()
            if not designation:
                QMessageBox.information(
                    self, "Designation required", "Please enter a Pango name to validate."
                )
                return

            try:
                resolved = unroll_pango_name(designation, self._alias_map)
            except (TypeError, ValueError) as exc:
                self._result.setPlainText(str(exc))
            else:
                self._result.setPlainText(resolved)

        def _on_show_ancestry(self) -> None:
            designation = self._alias_input.text().strip()
            if not designation:
                QMessageBox.information(
                    self,
                    "Designation required",
                    "Please enter a Pango name to resolve its ancestry.",
                )
                return

            try:
                ancestry = get_ancestral_dict(designation, self._alias_map)
            except (TypeError, ValueError) as exc:
                self._result.setPlainText(str(exc))
            else:
                self._result.setPlainText(_format_ancestry(ancestry))

        def _on_save_alias_report(self) -> None:
            try:
                rows = generate_alias_ancestry_report(self._alias_map)
            except (TypeError, ValueError) as exc:
                QMessageBox.critical(self, "Failed to build report", str(exc))
                return

            if not rows:
                QMessageBox.information(
                    self,
                    "No aliases",
                    "No non-root aliases were found to include in the report.",
                )
                return

            path = default_report_path()

            try:
                write_alias_ancestry_workbook(rows, path)
            except OSError as exc:  # pragma: no cover - filesystem failures are runtime issues
                QMessageBox.critical(
                    self,
                    "Failed to save report",
                    f"Could not write report to {path}: {exc}",
                )
                return

            self._result.setPlainText(f"Saved alias ancestry report to {path}")

        def _on_select_file(self) -> None:
            dialog = QFileDialog(self, "Select alias mapping JSON")
            dialog.setNameFilters(["JSON files (*.json)", "All files (*)"])
            dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
            if dialog.exec() == QFileDialog.DialogCode.Accepted:
                selected = dialog.selectedFiles()
                if not selected:
                    return
                path = Path(selected[0])
                try:
                    self._alias_map = load_alias_map(path)
                except Exception as exc:  # pragma: no cover - GUI feedback path
                    QMessageBox.critical(
                        self,
                        "Failed to load alias mapping",
                        f"Could not load alias mapping from {path}: {exc}",
                    )
                    return

                self._current_path = path
                self._status.setText(self._status_text())
                self._result.clear()

    import sys

    app = QApplication.instance()
    owns_app = False
    if app is None:
        app = QApplication(sys.argv)
        owns_app = True

    window = AliasLookupWindow(alias_map_path)
    window.show()

    if owns_app:
        app.exec()


if __name__ == "__main__":  # pragma: no cover - manual GUI invocation
    run_gui()

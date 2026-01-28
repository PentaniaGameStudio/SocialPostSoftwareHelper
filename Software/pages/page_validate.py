# Software/pages/page_validate.py
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QLabel
)
from PySide6.QtCore import Signal

from state import AppState
from validators import validate_database


class PageValidate(QWidget):
    navigateRequested = Signal(str)
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state

        self.label = QLabel("Vérifie l’intégrité du JSON (références, types, IDs).")
        self.btn_run = QPushButton("Vérifier maintenant")

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Niveau", "Chemin", "Message"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(self.table.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(self.table.EditTrigger.NoEditTriggers)

        top = QHBoxLayout()
        top.addWidget(self.btn_run)
        top.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addWidget(self.label)
        layout.addLayout(top)
        layout.addWidget(self.table)

        self.btn_run.clicked.connect(self.run_check)
        self.state.dataChanged.connect(self.run_check)
        self.table.itemDoubleClicked.connect(self._on_double_click)

    def run_check(self) -> None:
        issues = validate_database(self.state.data)

        # Nettoyage PROPRE (indispensable)
        self.table.setSortingEnabled(False)
        self.table.clearContents()
        self.table.setRowCount(0)

        for it in issues:
            row = self.table.rowCount()
            self.table.insertRow(row)

            # Toujours créer de NOUVEAUX items
            level_item = QTableWidgetItem(it.level)
            path_item = QTableWidgetItem(it.path)
            msg_item = QTableWidgetItem(it.message)

            # Stockage du path pour la navigation
            path_item.setData(Qt.ItemDataRole.UserRole, it.path)

            if it.level == "ERROR":
                level_item.setForeground(Qt.GlobalColor.red)
            elif it.level == "WARN":
                level_item.setForeground(Qt.GlobalColor.darkYellow)

            self.table.setItem(row, 0, level_item)
            self.table.setItem(row, 1, path_item)
            self.table.setItem(row, 2, msg_item)

        self.table.setSortingEnabled(True)

        if not issues:
            self.label.setText("✅ Aucun problème détecté.")
        else:
            errors = sum(1 for x in issues if x.level == "ERROR")
            warns = sum(1 for x in issues if x.level == "WARN")
            self.label.setText(f"Résultat : {errors} erreur(s), {warns} warning(s).")


    def _on_double_click(self, item) -> None:
        # On récupère le path depuis la colonne "Chemin" (1)
        row = item.row()
        path_item = self.table.item(row, 1)
        if not path_item:
            return
        path = path_item.data(Qt.ItemDataRole.UserRole)
        if isinstance(path, str) and path:
            self.navigateRequested.emit(path)

from __future__ import annotations

from contextlib import contextmanager

from PySide6.QtWidgets import QWidget, QHBoxLayout, QMessageBox, QInputDialog, QLineEdit
from PySide6.QtCore import Qt

from state import AppState
from ui_helpers import ListPanel
import copy


class PageUsernames(QWidget):
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self._building_ui = False

        self._build_ui()

        self.state.dataChanged.connect(self.reload_from_state)
        self.reload_from_state()

    @contextmanager
    def _ui_guard(self):
        self._building_ui = True
        try:
            yield
        finally:
            self._building_ui = False

    def _set_dirty(self) -> None:
        self.state.mark_dirty()
        self.state.dataChanged.emit()
        
    def goto_pool(self, pool_id: str) -> None:
        with self._ui_guard():
            self._refresh_categories(preserve_selection=False)
            found = self.panel_categories.list.findItems(pool_id, Qt.MatchExactly)
            if found:
                self.panel_categories.list.setCurrentItem(found[0])
                self.panel_categories.list.scrollToItem(found[0])
                self._refresh_names()


    def _pools(self) -> dict:
        return self.state.data.setdefault("usernames", {})

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)

        self.panel_categories = ListPanel(placeholder="Add category… (Enter)")
        self.panel_names = ListPanel(placeholder="Add username… (Enter)")

        # Handlers catégories
        self.panel_categories.set_handlers(
            on_add=self._add_category,
            on_edit=self._edit_category,
            on_delete=self._delete_category,
            on_selection_changed=self._on_category_changed,
        )

        # Handlers usernames
        self.panel_names.set_handlers(
            on_add=self._add_name,
            on_edit=self._edit_name,
            on_delete=self._delete_name,
        )
        
        self.panel_categories.set_clipboard_handlers(
            pack=self._pack_category,
            paste=self._paste_category,
        )


        root.addWidget(self.panel_categories, 1)
        root.addWidget(self.panel_names, 2)


    def _pack_category(self) -> object | None:
        cat = self.panel_categories.current_text()
        if not cat:
            return None

        pools = self._pools()
        return {
            "kind": "username_category",
            "id": cat,
            "data": copy.deepcopy(pools.get(cat, [])),
        }

    def _paste_category(self, payload: object) -> bool:
        if not isinstance(payload, dict) or payload.get("kind") != "username_category":
            return False

        pools = self._pools()
        base = str(payload.get("id") or "Category")
        data = payload.get("data") or []
        if not isinstance(data, list):
            return False

        new_id = ListPanel.make_unique_name(base, exists=lambda s: s in pools)
        pools[new_id] = list(data)

        self._set_dirty()
        self._refresh_categories(preserve_selection=False)
        found = self.panel_categories.list.findItems(new_id, Qt.MatchExactly)
        if found:
            self.panel_categories.list.setCurrentItem(found[0])
            self.panel_categories.list.scrollToItem(found[0])

        return True

    def reload_from_state(self) -> None:
        with self._ui_guard():
            self._refresh_categories(preserve_selection=True)
            self._refresh_names()

    def _current_category(self) -> str | None:
        return self.panel_categories.current_text()

    def _current_name(self) -> str | None:
        return self.panel_names.current_text()

    def _refresh_categories(self, preserve_selection: bool) -> None:
        items = sorted(self._pools().keys())
        self.panel_categories.set_items(items, preserve_selection=preserve_selection)

    def _refresh_names(self) -> None:
        cat = self._current_category()
        pools = self._pools()

        if not cat:
            self.panel_names.set_items([], preserve_selection=False)
            self.panel_names.setEnabled(False)
            return

        self.panel_names.setEnabled(True)
        self.panel_names.set_items(list(pools.get(cat, [])), preserve_selection=True)

    def _on_category_changed(self) -> None:
        if self._building_ui:
            return
        self._refresh_names()

    # -------------------------
    # Categories CRUD
    # -------------------------
    def _add_category(self, name: str) -> None:
        pools = self._pools()
        if name in pools:
            QMessageBox.warning(self, "Erreur", "Cette catégorie existe déjà.")
            return

        pools[name] = []
        self.panel_categories.clear_input()
        self._set_dirty()

        with self._ui_guard():
            self._refresh_categories(preserve_selection=False)
            found = self.panel_categories.list.findItems(name, Qt.MatchExactly)
            if found:
                self.panel_categories.list.setCurrentItem(found[0])
            self._refresh_names()

    def _edit_category(self, typed: str) -> None:
        old = self._current_category()
        if not old:
            return

        if not typed:
            self.panel_categories.input.setText(old)
            self.panel_categories.focus_input(select_all=True)
            return

        new = typed.strip()
        if not new or new == old:
            self.panel_categories.clear_input()
            return

        pools = self._pools()
        if new in pools:
            QMessageBox.warning(self, "Erreur", "Une catégorie avec ce nom existe déjà.")
            return

        # ✅ rename + propagation (commentBlocks.usernamePool) + dataChanged
        if not self.state.rename_username_pool(old, new):
            return

        # Le dataChanged va reload toutes les pages, donc on évite les refresh manuels “trop”
        # mais on peut quand même nettoyer l’input ici
        self.panel_categories.clear_input()

    def _delete_category(self) -> None:
        cat = self._current_category()
        if not cat:
            return

        res = QMessageBox.question(
            self,
            "Supprimer",
            f"Supprimer la catégorie '{cat}' ?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if res != QMessageBox.Yes:
            return

        self._pools().pop(cat, None)
        self._set_dirty()

        with self._ui_guard():
            self._refresh_categories(preserve_selection=False)
            self._refresh_names()

    # -------------------------
    # Names CRUD
    # -------------------------
    def _add_name(self, name: str) -> None:
        cat = self._current_category()
        if not cat:
            return

        pools = self._pools()
        names = pools.setdefault(cat, [])

        typed = (name or "").strip()
        if not typed:
            return

        # Si déjà présent : on propose une édition avant d'ajouter
        if typed in names:
            # Boucle : tant que l'utilisateur propose un nom déjà pris, on redemande
            current = typed
            while True:
                new_name, ok = QInputDialog.getText(
                    self,
                    "Username déjà présent",
                    "Ce username existe déjà dans ce set.\nModifie-le pour l'ajouter :",
                    QLineEdit.Normal,
                    current
                )
                if not ok:
                    # Annule => on ne fait rien
                    self.panel_names.clear_input()
                    return

                new_name = (new_name or "").strip()
                if not new_name:
                    QMessageBox.warning(self, "Erreur", "Le username ne peut pas être vide.")
                    current = ""
                    continue

                if new_name in names:
                    QMessageBox.warning(self, "Erreur", "Ce username existe déjà dans cette catégorie.")
                    current = new_name
                    continue

                typed = new_name
                break

        # Ajout (soit direct, soit après édition)
        names.append(typed)
        self.panel_names.clear_input()
        self._set_dirty()
        self._refresh_names()

    def _edit_name(self, typed: str) -> None:
        cat = self._current_category()
        old = self._current_name()
        if not cat or not old:
            return

        if not typed:
            self.panel_names.input.setText(old)
            self.panel_names.focus_input(select_all=True)
            return

        new = typed
        if new == old:
            self.panel_names.clear_input()
            return

        pools = self._pools()
        names = pools.get(cat, [])

        if new in names:
            QMessageBox.warning(self, "Erreur", "Ce username existe déjà dans cette catégorie.")
            return

        try:
            idx = names.index(old)
        except ValueError:
            return

        names[idx] = new
        self.panel_names.clear_input()
        self._set_dirty()
        self._refresh_names()

    def _delete_name(self) -> None:
        cat = self._current_category()
        old = self._current_name()
        if not cat or not old:
            return

        names = self._pools().get(cat, [])
        try:
            names.remove(old)
        except ValueError:
            return

        self._set_dirty()
        self._refresh_names()

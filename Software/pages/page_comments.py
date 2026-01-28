from __future__ import annotations

from contextlib import contextmanager

from PySide6.QtCore import Qt, QSignalBlocker
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QTabWidget,
    QLabel, QComboBox, QMessageBox, QInputDialog, QPushButton
)

from state import AppState
from ui_helpers import ListPanel
import copy

class PageComments(QWidget):
    """
    Edition:
    - Comment Blocks : usernamePool + liste de textes
    - Comment Sets   : composition ordonnée de blocks
    """

    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self._building_ui = False

        self._build_ui()

        self.state.dataChanged.connect(self.reload_from_state)
        self.reload_from_state()

    # =========================================================
    # Guard / data access
    # =========================================================
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

    def goto_set(self, set_id: str) -> None:
        with self._ui_guard():
            self._refresh_sets(preserve_selection=False)
            found = self.panel_sets.list.findItems(set_id, Qt.MatchExactly)
            if found:
                self.panel_sets.list.setCurrentItem(found[0])
                self.panel_sets.list.scrollToItem(found[0])

    def goto_block(self, block_id: str) -> None:
        # Assure-toi que la liste des blocks est rafraîchie selon ton set courant.
        with self._ui_guard():
            self._refresh_blocks()
            found = self.panel_blocks.list.findItems(block_id, Qt.MatchExactly)
            if found:
                self.panel_blocks.list.setCurrentItem(found[0])
                self.panel_blocks.list.scrollToItem(found[0])


    def _get_usernames(self) -> dict:
        return self.state.data.setdefault("usernames", {})

    def _get_blocks(self) -> dict:
        return self.state.data.setdefault("commentBlocks", {})

    def _get_sets(self) -> dict:
        return self.state.data.setdefault("commentSets", {})

    def _current_block_id(self) -> str | None:
        return self.panel_blocks.current_text()

    def _current_set_id(self) -> str | None:
        return self.panel_sets.current_text()

    def _current_block_text(self) -> str | None:
        return self.panel_texts.current_text()

    def _current_set_block(self) -> str | None:
        return self.panel_set_blocks.current_text()

    # =========================================================
    # UI
    # =========================================================
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)

        self.tab_blocks = QWidget()
        self.tab_sets = QWidget()

        self.tabs.addTab(self.tab_blocks, "Blocks")
        self.tabs.addTab(self.tab_sets, "Sets")

        root.addWidget(self.tabs)

        self._build_blocks_tab()
        self._build_sets_tab()

    def _build_blocks_tab(self) -> None:
        layout = QHBoxLayout(self.tab_blocks)

        # ---- Left: blocks list (ListPanel)
        left = QVBoxLayout()
        left.addWidget(QLabel("Comment Blocks"))

        self.panel_blocks = ListPanel(placeholder="Add block id… (Enter)")
        self.panel_blocks.set_handlers(
            on_add=self._add_block_from_text,
            on_edit=self._rename_block_from_text,
            on_delete=self._delete_block,
            on_selection_changed=self._on_block_changed,
        )
        self.panel_blocks.set_clipboard_handlers(
            pack=self._pack_block,
            paste=self._paste_block,
        )

        left.addWidget(self.panel_blocks, 1)

        # ---- Right: block details (pool + texts)
        right = QVBoxLayout()

        pool_row = QHBoxLayout()
        pool_row.addWidget(QLabel("Username pool:"))
        self.combo_pool = QComboBox()
        self.combo_pool.currentIndexChanged.connect(self._on_pool_changed)
        pool_row.addWidget(self.combo_pool, 1)

        right.addLayout(pool_row)

        right.addWidget(QLabel("Texts:"))

        # Text list panel (ListPanel)
        # - Enter: add (support multi-lines)
        # - Edit: remplace la sélection par le champ (si vide -> pré-remplit)
        # - Delete: supprime l'item sélectionné
        self.panel_texts = ListPanel(
            placeholder="Add text… (Enter). You can paste multiple lines.",
            edit_label="Edit",
            delete_label="Delete",
        )
        self.panel_texts.set_handlers(
            on_add=self._add_text_from_text,
            on_edit=self._edit_text_from_text,
            on_delete=self._delete_text,
        )

        right.addWidget(self.panel_texts, 1)

        layout.addLayout(left, 1)
        layout.addLayout(right, 2)

    def _build_sets_tab(self) -> None:
        layout = QHBoxLayout(self.tab_sets)

        # ---- Left: sets list
        left = QVBoxLayout()
        left.addWidget(QLabel("Comment Sets"))

        self.panel_sets = ListPanel(placeholder="Add set id… (Enter)")
        self.panel_sets.set_handlers(
            on_add=self._add_set_from_text,
            on_edit=self._rename_set_from_text,
            on_delete=self._delete_set,
            on_selection_changed=self._on_set_changed,
        )
        self.panel_sets.set_clipboard_handlers(
            pack=self._pack_set,
            paste=self._paste_set,
        )

        left.addWidget(self.panel_sets, 1)

        # ---- Right: ordered blocks inside set
        right = QVBoxLayout()
        right.addWidget(QLabel("Blocks in set (ordered):"))

        # Ligne Combo + Add
        add_row = QHBoxLayout()
        self.combo_blocks_in_set = QComboBox()
        self.btn_add_block_to_set = QPushButton("Add")
        self.btn_add_block_to_set.clicked.connect(self._add_block_to_set_from_combo)

        add_row.addWidget(self.combo_blocks_in_set, 1)
        add_row.addWidget(self.btn_add_block_to_set, 0)

        # Liste réordonnable + boutons Edit/Delete du ListPanel
        self.panel_set_blocks = ListPanel(
            placeholder="",          # inutilisé
            edit_label="Edit",
            delete_label="Remove",
            enable_reorder=True,
        )
        # On n'utilise plus la saisie clavier pour Add/Edit
        self.panel_set_blocks.set_handlers(
            on_add=None,  # Add géré par le bouton au-dessus
            on_edit=self._edit_set_block_from_combo,
            on_delete=self._remove_block_from_set,
            on_rows_moved=self._on_set_blocks_reordered,
        )

        # Cache le champ texte (et le bouton Add interne s'il existe)
        if hasattr(self.panel_set_blocks, "input") and self.panel_set_blocks.input:
            self.panel_set_blocks.input.hide()
        if hasattr(self.panel_set_blocks, "btn_add") and self.panel_set_blocks.btn_add:
            self.panel_set_blocks.btn_add.hide()

        right.addWidget(self.panel_set_blocks, 1)
        # --- Insère la combo + Add DANS le ListPanel, juste avant la rangée des boutons
        panel_layout = self.panel_set_blocks.layout()  # QVBoxLayout interne du ListPanel

        # Sécurité : si le layout interne n'existe pas, fallback (rare)
        if panel_layout is None:
            right.addLayout(add_row)
        else:
            # On insère "add_row" juste avant le dernier item du panel (souvent la row des boutons)
            insert_index = max(0, panel_layout.count() - 1)
            panel_layout.insertLayout(insert_index, add_row)


        layout.addLayout(left, 1)
        layout.addLayout(right, 2)


    # =========================================================
    # Reload / refresh
    # =========================================================
    def _refresh_blocks_combo_for_sets(self) -> None:
        blocks = sorted(self._get_blocks().keys())
        old = self.combo_blocks_in_set.currentText()

        with QSignalBlocker(self.combo_blocks_in_set):
            self.combo_blocks_in_set.clear()
            self.combo_blocks_in_set.addItems(blocks)
            if old in blocks:
                self.combo_blocks_in_set.setCurrentText(old)


    def reload_from_state(self) -> None:
        with self._ui_guard():
            self._get_blocks()
            self._get_sets()

            self._refresh_pool_combo()
            self._refresh_blocks_list(preserve_selection=True)
            self._refresh_blocks_combo_for_sets()
            self._refresh_sets_list(preserve_selection=True)

            self._refresh_block_details()
            self._refresh_set_details()

    def _refresh_pool_combo(self) -> None:
        pools = sorted(self._get_usernames().keys())
        old = self.combo_pool.currentText()

        with QSignalBlocker(self.combo_pool):
            self.combo_pool.clear()
            self.combo_pool.addItems(pools)
            if old in pools:
                self.combo_pool.setCurrentText(old)

    def _refresh_blocks_list(self, preserve_selection: bool) -> None:
        blocks = self._get_blocks()
        self.panel_blocks.set_items(sorted(blocks.keys()), preserve_selection=preserve_selection)

    def _refresh_sets_list(self, preserve_selection: bool) -> None:
        sets = self._get_sets()
        self.panel_sets.set_items(sorted(sets.keys()), preserve_selection=preserve_selection)

    def _refresh_block_details(self) -> None:
        bid = self._current_block_id()
        blocks = self._get_blocks()

        if not bid or bid not in blocks:
            self.combo_pool.setEnabled(False)
            self.panel_texts.set_items([], preserve_selection=False)
            self.panel_texts.setEnabled(False)
            return

        self.combo_pool.setEnabled(True)
        self.panel_texts.setEnabled(True)

        block = blocks.get(bid, {})
        pool = block.get("usernamePool", "")

        with QSignalBlocker(self.combo_pool):
            if pool:
                self.combo_pool.setCurrentText(pool)

        texts = list(block.get("comments", []))
        self.panel_texts.set_items(texts, preserve_selection=True)

    def _refresh_set_details(self) -> None:
        sid = self._current_set_id()
        sets = self._get_sets()

        if not sid or sid not in sets:
            self.panel_set_blocks.set_items([], preserve_selection=False)
            self.panel_set_blocks.setEnabled(False)
            return

        self.panel_set_blocks.setEnabled(True)
        self.panel_set_blocks.set_items(list(sets.get(sid, [])), preserve_selection=True)

    # =========================================================
    # Events (selection / combo)
    # =========================================================
    def _on_block_changed(self) -> None:
        if self._building_ui:
            return
        self._refresh_block_details()

    def _on_set_changed(self) -> None:
        if self._building_ui:
            return
        self._refresh_set_details()

    def _on_pool_changed(self) -> None:
        if self._building_ui:
            return

        bid = self._current_block_id()
        if not bid:
            return

        pool = self.combo_pool.currentText().strip()

        blocks = self._get_blocks()
        blocks.setdefault(bid, {}).setdefault("comments", [])
        blocks[bid]["usernamePool"] = pool

        self._set_dirty()

    # =========================================================
    # Blocks CRUD (ListPanel)
    # =========================================================
    def _pack_block(self) -> object | None:
        bid = self._current_block_id()
        if not bid:
            return None

        blocks = self._get_blocks()
        if bid not in blocks:
            return None

        return {
            "kind": "comment_block",
            "id": bid,
            "data": copy.deepcopy(blocks[bid]),
        }

    def _paste_block(self, payload: object) -> bool:
        if not isinstance(payload, dict) or payload.get("kind") != "comment_block":
            return False

        blocks = self._get_blocks()

        base_id = str(payload.get("id") or "Block").strip() or "Block"
        data = payload.get("data")
        if not isinstance(data, dict):
            return False

        # Nouveau block id unique
        new_id = ListPanel.make_unique_name(base_id, exists=lambda s: s in blocks)

        # Copie profonde
        new_data = copy.deepcopy(data)

        # Sécurise la structure attendue
        new_data.setdefault("usernamePool", self._default_pool_for_new_block())
        if not isinstance(new_data.get("comments"), list):
            new_data["comments"] = []

        blocks[new_id] = new_data

        self._set_dirty()

        # Refresh UI + sélection du nouveau block
        with self._ui_guard():
            self._refresh_blocks_list(preserve_selection=False)
            found = self.panel_blocks.list.findItems(new_id, Qt.MatchExactly)
            if found:
                self.panel_blocks.list.setCurrentItem(found[0])
                self.panel_blocks.list.scrollToItem(found[0])
            self._refresh_block_details()

            # Optionnel : si tu veux que la combo "Blocks in set" soit à jour tout de suite
            self._refresh_blocks_combo_for_sets()

        return True

    def _default_pool_for_new_block(self) -> str:
        pools = sorted(self._get_usernames().keys())
        if "Global" in pools:
            return "Global"
        return pools[0] if pools else ""

    def _add_block_from_text(self, name: str) -> None:
        name = name.strip()
        if not name:
            return

        blocks = self._get_blocks()
        if name in blocks:
            QMessageBox.warning(self, "Erreur", "Ce block existe déjà.")
            return

        blocks[name] = {"usernamePool": self._default_pool_for_new_block(), "comments": []}
        self.panel_blocks.clear_input()
        self._set_dirty()

        with self._ui_guard():
            self._refresh_blocks_list(preserve_selection=False)
            found = self.panel_blocks.list.findItems(name, Qt.MatchExactly)
            if found:
                self.panel_blocks.list.setCurrentItem(found[0])
            self._refresh_block_details()

    def _add_block_to_set_from_combo(self) -> None:
        sid = self._current_set_id()
        if not sid:
            return

        bid = self.combo_blocks_in_set.currentText().strip()
        if not bid:
            return

        # bid est forcément valide puisque vient de la combo
        sets = self._get_sets()
        arr = sets.setdefault(sid, [])
        arr.append(bid)

        self._set_dirty()
        self._refresh_set_details()
        
    def _edit_set_block_from_combo(self, _typed_unused: str = "") -> None:
        sid = self._current_set_id()
        old = self._current_set_block()
        if not sid or not old:
            return

        new = self.combo_blocks_in_set.currentText().strip()
        if not new:
            return

        sets = self._get_sets()
        arr = sets.setdefault(sid, [])

        row = self.panel_set_blocks.list.currentRow()
        if 0 <= row < len(arr):
            arr[row] = new
        else:
            # fallback : première occurrence
            try:
                idx = arr.index(old)
                arr[idx] = new
            except ValueError:
                return

        self._set_dirty()
        self._refresh_set_details()

    def _rename_block_from_text(self, typed: str) -> None:
        old = self._current_block_id()
        if not old:
            return

        if not typed:
            self.panel_blocks.input.setText(old)
            self.panel_blocks.focus_input(select_all=True)
            return

        new = typed.strip()
        if not new or new == old:
            self.panel_blocks.clear_input()
            return

        blocks = self._get_blocks()
        if new in blocks:
            QMessageBox.warning(self, "Erreur", "Un block avec ce nom existe déjà.")
            return

        # rename block
        blocks[new] = blocks.pop(old)

        # remplace dans tous les sets
        sets = self._get_sets()
        for sid, arr in sets.items():
            sets[sid] = [new if x == old else x for x in arr]

        self.panel_blocks.clear_input()
        self._set_dirty()

        with self._ui_guard():
            self._refresh_blocks_list(preserve_selection=False)
            self._refresh_sets_list(preserve_selection=True)

            found = self.panel_blocks.list.findItems(new, Qt.MatchExactly)
            if found:
                self.panel_blocks.list.setCurrentItem(found[0])

            self._refresh_block_details()
            self._refresh_set_details()

    def _delete_block(self) -> None:
        bid = self._current_block_id()
        if not bid:
            return

        # warn si utilisé
        used_in = []
        for sid, arr in self._get_sets().items():
            if bid in arr:
                used_in.append(sid)

        msg = f"Supprimer le block '{bid}' ?"
        if used_in:
            msg += "\n\nAttention: utilisé dans ces sets:\n- " + "\n- ".join(used_in)

        res = QMessageBox.question(self, "Supprimer", msg, QMessageBox.Yes | QMessageBox.No)
        if res != QMessageBox.Yes:
            return

        self._get_blocks().pop(bid, None)
        self._set_dirty()

        with self._ui_guard():
            self._refresh_blocks_list(preserve_selection=False)
            self._refresh_block_details()
            self._refresh_set_details()

    # =========================================================
    # Texts CRUD (ListPanel)
    # =========================================================
    def _pack_set(self) -> object | None:
        sid = self._current_set_id()
        if not sid:
            return None

        sets = self._get_sets()
        if sid not in sets:
            return None

        return {
            "kind": "comment_set",
            "id": sid,
            "data": copy.deepcopy(sets[sid]),
        }

    def _paste_set(self, payload: object) -> bool:
        if not isinstance(payload, dict) or payload.get("kind") != "comment_set":
            return False

        sets = self._get_sets()

        base_id = str(payload.get("id") or "Set").strip() or "Set"
        data = payload.get("data")
        if not isinstance(data, list):
            return False

        new_id = ListPanel.make_unique_name(base_id, exists=lambda s: s in sets)
        sets[new_id] = list(data)

        self._set_dirty()

        with self._ui_guard():
            self._refresh_sets_list(preserve_selection=False)
            found = self.panel_sets.list.findItems(new_id, Qt.MatchExactly)
            if found:
                self.panel_sets.list.setCurrentItem(found[0])
                self.panel_sets.list.scrollToItem(found[0])
            self._refresh_set_details()

        return True
    
    def _add_text_from_text(self, raw: str) -> None:
        bid = self._current_block_id()
        if not bid:
            return

        # Permet paste multi-lignes même si Enter ne valide que "returnPressed"
        lines = [line.strip() for line in raw.splitlines()]
        lines = [line for line in lines if line]
        if not lines:
            return

        blocks = self._get_blocks()
        arr = blocks.setdefault(bid, {}).setdefault("comments", [])
        arr.extend(lines)

        self.panel_texts.clear_input()
        self._set_dirty()
        self._refresh_block_details()

    def _edit_text_from_text(self, typed: str) -> None:
        bid = self._current_block_id()
        old = self._current_block_text()
        if not bid or not old:
            return

        if not typed:
            self.panel_texts.input.setText(old)
            self.panel_texts.focus_input(select_all=True)
            return

        new = typed.strip()
        if not new:
            return

        blocks = self._get_blocks()
        arr = blocks.setdefault(bid, {}).setdefault("comments", [])

        # remplace la première occurrence (cohérent avec ton ancien code)
        try:
            idx = arr.index(old)
            arr[idx] = new
        except ValueError:
            return

        self.panel_texts.clear_input()
        self._set_dirty()
        self._refresh_block_details()

    def _delete_text(self) -> None:
        bid = self._current_block_id()
        old = self._current_block_text()
        if not bid or not old:
            return

        blocks = self._get_blocks()
        arr = blocks.setdefault(bid, {}).setdefault("comments", [])

        try:
            arr.remove(old)
        except ValueError:
            return

        self._set_dirty()
        self._refresh_block_details()

    # =========================================================
    # Sets CRUD (ListPanel)
    # =========================================================
    def _add_set_from_text(self, name: str) -> None:
        name = name.strip()
        if not name:
            return

        sets = self._get_sets()
        if name in sets:
            QMessageBox.warning(self, "Erreur", "Ce set existe déjà.")
            return

        sets[name] = []
        self.panel_sets.clear_input()
        self._set_dirty()

        with self._ui_guard():
            self._refresh_sets_list(preserve_selection=False)
            found = self.panel_sets.list.findItems(name, Qt.MatchExactly)
            if found:
                self.panel_sets.list.setCurrentItem(found[0])
            self._refresh_set_details()

    # Software/pages/page_comments.py
    def _rename_set_from_text(self, typed: str) -> None:
        old = self._current_set_id()
        if not old:
            return

        if not typed:
            self.panel_sets.input.setText(old)
            self.panel_sets.focus_input(select_all=True)
            return

        new = typed.strip()
        if not new or new == old:
            self.panel_sets.clear_input()
            return

        sets = self._get_sets()
        if new in sets:
            QMessageBox.warning(self, "Erreur", "Ce set existe déjà.")
            return

        # ✅ rename + propagation (posts.commentsSet) + dataChanged
        if not self.state.rename_comment_set(old, new):
            return

        self.panel_sets.clear_input()
        
    def _delete_set(self) -> None:
        sid = self._current_set_id()
        if not sid:
            return

        res = QMessageBox.question(
            self, "Supprimer", f"Supprimer le set '{sid}' ?",
            QMessageBox.Yes | QMessageBox.No
        )
        if res != QMessageBox.Yes:
            return

        self._get_sets().pop(sid, None)
        self._set_dirty()

        with self._ui_guard():
            self._refresh_sets_list(preserve_selection=False)
            self._refresh_set_details()

    # =========================================================
    # Set composition (ListPanel + reorder)
    # =========================================================

    def _remove_block_from_set(self) -> None:
        sid = self._current_set_id()
        current = self._current_set_block()
        if not sid or not current:
            return

        sets = self._get_sets()
        arr = sets.setdefault(sid, [])

        row = self.panel_set_blocks.list.currentRow()
        if 0 <= row < len(arr):
            arr.pop(row)
        else:
            try:
                arr.remove(current)
            except ValueError:
                return

        self._set_dirty()
        self._refresh_set_details()

    def _on_set_blocks_reordered(self) -> None:
        """Quand l'utilisateur réordonne via drag&drop, on réécrit l'ordre dans le JSON."""
        if self._building_ui:
            return

        sid = self._current_set_id()
        if not sid:
            return

        sets = self._get_sets()
        arr = sets.setdefault(sid, [])

        # Réécrit arr depuis l'ordre visuel
        new_arr = [self.panel_set_blocks.list.item(i).text() for i in range(self.panel_set_blocks.list.count())]
        arr[:] = new_arr

        self._set_dirty()

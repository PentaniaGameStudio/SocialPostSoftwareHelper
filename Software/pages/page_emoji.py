from __future__ import annotations

from contextlib import contextmanager

from PySide6.QtCore import Qt, QSignalBlocker
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QAbstractItemView,
    QFormLayout, QLineEdit, QLabel, QMessageBox, QGroupBox
)

from state import AppState
from ui_helpers import ListPanel
import copy

class PageEmoji(QWidget):
    """
    Gestion des presets emoji (up/down/heart/comment) avec min/max + order (uniquement pour le software).

    JSON:
    {
      "emojiPresets": {
        "CATELF_EMOJI_NORMAL": {
          "order": 0,
          "up": {"min": 90, "max": 190},
          "down": {"min": 0, "max": 4},
          "heart": {"min": 20, "max": 60},
          "comment": {"min": 8, "max": 22}
        }
      }
    }
    """

    KEYS = ("up", "down", "heart", "comment")

    EMOJI_LABELS = {
        "up": "👍",
        "down": "👎",
        "heart": "❤️",
        "comment": "💬",
    }

    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self._building_ui = False

        self._build_ui()

        self.state.dataChanged.connect(self.reload_from_state)
        self.reload_from_state()

    # =========================================================
    # Helpers / state
    # =========================================================
    @contextmanager
    def _ui_guard(self):
        """Bloque temporairement les effets de bord (dirty/écriture) durant un refresh UI."""
        self._building_ui = True
        try:
            yield
        finally:
            self._building_ui = False

    def _get_presets(self) -> dict:
        return self.state.data.setdefault("emojiPresets", {})

    def _current_preset_id(self) -> str | None:
        return self.panel_presets.current_text()

    def _default_preset(self) -> dict:
        return {
            "order": 0,
            "up": {"min": 0, "max": 0},
            "down": {"min": 0, "max": 0},
            "heart": {"min": 0, "max": 0},
            "comment": {"min": 0, "max": 0},
        }

    @staticmethod
    def _to_int(text: str, default: int = 0) -> int:
        try:
            return int(text) if text.strip() else default
        except ValueError:
            return default

    @staticmethod
    def _clamp_nonneg(value: int) -> int:
        return value if value >= 0 else 0


    def _set_dirty(self) -> None:
        self.state.mark_dirty()
        self.state.dataChanged.emit()

    def goto_preset(self, preset_id: str) -> None:
        with self._ui_guard():
            self._refresh_presets(preserve_selection=False)
            found = self.panel_presets.list.findItems(preset_id, Qt.MatchExactly)
            if found:
                self.panel_presets.list.setCurrentItem(found[0])
                self.panel_presets.list.scrollToItem(found[0])


    # =========================================================
    # UI
    # =========================================================
    def _build_ui(self) -> None:
        root = QHBoxLayout(self)

        # -------- Left: presets panel (ListPanel) + drag&drop
        left = QVBoxLayout()
        left.addWidget(QLabel("Emoji Presets"))

        self.panel_presets = ListPanel(placeholder="Add preset… (Enter)")
        left.addWidget(self.panel_presets, 1)

        # Drag & drop interne pour réordonner (sur le QListWidget du panel)
        self.panel_presets.list.setDragEnabled(True)
        self.panel_presets.list.setAcceptDrops(True)
        self.panel_presets.list.setDropIndicatorShown(True)
        self.panel_presets.list.setDefaultDropAction(Qt.MoveAction)
        self.panel_presets.list.setDragDropMode(QAbstractItemView.InternalMove)

        # Capte le ré-ordonnancement (signal du modèle)
        self.panel_presets.list.model().rowsMoved.connect(self._on_presets_reordered)

        # Handlers standard du panel
        self.panel_presets.set_handlers(
            on_add=self._add_preset_from_text,
            on_edit=self._rename_preset_from_text,
            on_delete=self._delete_preset,
            on_selection_changed=self._on_preset_changed,
        )
        
        self.panel_presets.set_clipboard_handlers(
            pack=self._pack_preset,
            paste=self._paste_preset,
        )


        # -------- Right: editor
        right = QVBoxLayout()
        right.addWidget(QLabel("Preset values"))

        self.group_editor = QGroupBox("Edit")
        editor_layout = QFormLayout(self.group_editor)

        # Validation ints >= 0
        self._int_validator = QIntValidator(0, 999999, self)

        # Champs: (key, subkey) -> QLineEdit
        self.inputs: dict[tuple[str, str], QLineEdit] = {}

        for key in self.KEYS:
            label = self.EMOJI_LABELS.get(key, key)
            box = QGroupBox(f"{label} {key}")
            f = QFormLayout(box)

            le_min = QLineEdit()
            le_max = QLineEdit()
            le_min.setValidator(self._int_validator)
            le_max.setValidator(self._int_validator)

            le_min.editingFinished.connect(lambda k=key: self._on_value_changed(k))
            le_max.editingFinished.connect(lambda k=key: self._on_value_changed(k))

            self.inputs[(key, "min")] = le_min
            self.inputs[(key, "max")] = le_max

            f.addRow("Min", le_min)
            f.addRow("Max", le_max)

            editor_layout.addRow(box)

        right.addWidget(self.group_editor, 1)

        hint = QLabel("Astuce: ces presets seront sélectionnables depuis les posts (page héroïne).")
        hint.setWordWrap(True)
        right.addWidget(hint)

        root.addLayout(left, 1)
        root.addLayout(right, 2)

    # =========================================================
    # Reload / refresh
    # =========================================================
    def reload_from_state(self) -> None:
        with self._ui_guard():
            self._get_presets()
            self._refresh_list(preserve_selection=True)
            self._refresh_editor()

    def _refresh_list(self, preserve_selection: bool) -> None:
        presets = self._get_presets()
        previous = self._current_preset_id() if preserve_selection else None

        ordered_ids = [
            pid for pid, _ in sorted(
                presets.items(),
                key=lambda kv: self._to_int(str(kv[1].get("order", 0)), 0),
            )
        ]

        # Utilise l'API du panel (préserve sélection)
        self.panel_presets.set_items(ordered_ids, preserve_selection=bool(previous))

        # Si preserve_selection=False, set_items sélectionne 0 si possible.
        # Si preserve_selection=True mais previous absent, set_items sélectionne 0 aussi.

    def _refresh_editor(self) -> None:
        pid = self._current_preset_id()
        presets = self._get_presets()

        enabled = bool(pid) and pid in presets
        self.group_editor.setEnabled(enabled)

        blockers = [QSignalBlocker(le) for le in self.inputs.values()]

        if not enabled:
            for le in self.inputs.values():
                le.setText("")
            return

        data = presets[pid]
        for key in self.KEYS:
            key_data = data.get(key, {})
            vmin = self._to_int(str(key_data.get("min", 0)), 0)
            vmax = self._to_int(str(key_data.get("max", 0)), 0)
            self.inputs[(key, "min")].setText(str(vmin))
            self.inputs[(key, "max")].setText(str(vmax))

    # =========================================================
    # Order handling
    # =========================================================
    def _rebuild_orders(self) -> None:
        presets = self._get_presets()
        for i in range(self.panel_presets.list.count()):
            pid = self.panel_presets.list.item(i).text()
            if pid in presets:
                presets[pid]["order"] = i

    # =========================================================
    # Events
    # =========================================================
    def _on_presets_reordered(self, *_args) -> None:
        if self._building_ui:
            return
        self._rebuild_orders()
        self._set_dirty()

    def _on_preset_changed(self) -> None:
        if self._building_ui:
            return
        with self._ui_guard():
            self._refresh_editor()

    def _pack_preset(self) -> object | None:
        pid = self._current_preset_id()
        if not pid:
            return None

        presets = self._get_presets()
        if pid not in presets:
            return None

        return {
            "kind": "emoji_preset",
            "id": pid,
            "data": copy.deepcopy(presets[pid]),
        }


    def _paste_preset(self, payload: object) -> bool:
        if not isinstance(payload, dict) or payload.get("kind") != "emoji_preset":
            return False

        presets = self._get_presets()

        base_id = str(payload.get("id") or "Preset").strip() or "Preset"
        data = payload.get("data")
        if not isinstance(data, dict):
            return False

        # Nom unique
        new_id = ListPanel.make_unique_name(base_id, exists=lambda s: s in presets)

        # Copie + order en fin (append)
        new_data = copy.deepcopy(data)

        # Recalage des orders existants puis append en fin
        self._rebuild_orders()
        new_data["order"] = self.panel_presets.list.count()

        presets[new_id] = new_data

        self._set_dirty()

        # Refresh UI + sélection
        with self._ui_guard():
            self._refresh_list(preserve_selection=False)
            found = self.panel_presets.list.findItems(new_id, Qt.MatchExactly)
            if found:
                self.panel_presets.list.setCurrentItem(found[0])
                self.panel_presets.list.scrollToItem(found[0])
            self._refresh_editor()

        return True


    # =========================================================
    # CRUD via ListPanel
    # =========================================================
    def _add_preset_from_text(self, name: str) -> None:
        name = name.strip()
        if not name:
            return

        presets = self._get_presets()
        if name in presets:
            QMessageBox.warning(self, "Erreur", "Ce preset existe déjà.")
            return

        # Append en fin (order = count) après recalage
        self._rebuild_orders()
        presets[name] = self._default_preset()
        presets[name]["order"] = self.panel_presets.list.count()

        self.panel_presets.clear_input()
        self._set_dirty()

        with self._ui_guard():
            self._refresh_list(preserve_selection=False)
            found = self.panel_presets.list.findItems(name, Qt.MatchExactly)
            if found:
                self.panel_presets.list.setCurrentItem(found[0])
            self._refresh_editor()

    # Software/pages/page_emoji.py
    def _rename_preset_from_text(self, typed: str) -> None:
        old = self._current_preset_id()
        if not old:
            return

        if not typed:
            self.panel_presets.input.setText(old)
            self.panel_presets.focus_input(select_all=True)
            return

        new = typed.strip()
        if not new or new == old:
            self.panel_presets.clear_input()
            return

        presets = self._get_presets()
        if new in presets:
            QMessageBox.warning(self, "Erreur", "Un preset avec ce nom existe déjà.")
            return

        # ✅ rename + propagation (posts.emojiPreset) + dataChanged
        if not self.state.rename_emoji_preset(old, new):
            return

        self.panel_presets.clear_input()


    def _delete_preset(self) -> None:
        pid = self._current_preset_id()
        if not pid:
            return

        res = QMessageBox.question(
            self,
            "Supprimer",
            f"Supprimer le preset '{pid}' ?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if res != QMessageBox.Yes:
            return

        presets = self._get_presets()
        presets.pop(pid, None)

        with self._ui_guard():
            self._refresh_list(preserve_selection=False)
            self._rebuild_orders()
            self._refresh_editor()

        self._set_dirty()

    # =========================================================
    # Values editing
    # =========================================================
    def _on_value_changed(self, key: str) -> None:
        if self._building_ui:
            return

        pid = self._current_preset_id()
        if not pid:
            return

        le_min = self.inputs[(key, "min")]
        le_max = self.inputs[(key, "max")]

        vmin = self._clamp_nonneg(self._to_int(le_min.text(), 0))
        vmax = self._clamp_nonneg(self._to_int(le_max.text(), 0))

        if vmin > vmax:
            vmax = vmin
            with QSignalBlocker(le_max):
                le_max.setText(str(vmax))

        presets = self._get_presets()
        preset = presets.setdefault(pid, self._default_preset())
        key_obj = preset.setdefault(key, {"min": 0, "max": 0})

        if key_obj.get("min") == vmin and key_obj.get("max") == vmax:
            return

        key_obj["min"] = vmin
        key_obj["max"] = vmax
        self._set_dirty()

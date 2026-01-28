# Software/pages/page_public_profile.py
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any

from PySide6.QtCore import Qt, QSignalBlocker
from PySide6.QtGui import QPixmap, QIntValidator
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QGroupBox,
    QLabel, QLineEdit, QTextEdit, QComboBox, QPushButton, QFrame,
    QFileDialog, QMessageBox, QHBoxLayout, QGridLayout, QAbstractItemView
)

from state import AppState
from social_editor_shell import SocialEditorShell, ShellTexts, HELP_EFFECT_JS, HELP_CONDITION_JS, TIME_SLOTS
from ui_helpers import NoWheelComboBox, ClickableImageLabel, ListPanel
import copy

PUBLIC_PROFILES_KEY = "profiles"

class ClickableImageLabel(QLabel):
    """QLabel image cliquable (double-clic) pour picker une image."""
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(180, 180)
        self.setStyleSheet("border: 1px solid #444; border-radius: 6px;")
        self.setText("Double-clic pour choisir\nune image")
        self.on_double_click = None  # callback
        self._pix_original: QPixmap | None = None

    def mouseDoubleClickEvent(self, event):
        if callable(self.on_double_click):
            self.on_double_click()
        super().mouseDoubleClickEvent(event)

    def set_original_pixmap(self, pix: QPixmap | None) -> None:
        """Stocke l'original et affiche en mode 'contain' (shrunk)."""
        self._pix_original = pix
        self._apply_scaled()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_scaled()

    def _apply_scaled(self) -> None:
        if not self._pix_original or self._pix_original.isNull():
            return
        scaled = self._pix_original.scaled(
            self.width(), self.height(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        self.setPixmap(scaled)


class PagePublicProfile(QWidget):
    """
    Page Profils Publics (multi-profils) utilisant SocialEditorShell:
      - Colonne gauche : Profiles (CRUD)
      - Colonne gauche : Posts (CRUD) dépend du profil sélectionné
      - Zone droite : éditeur Profile / Post (même UI que l'héroïne)

    Data (state.data):
      state.data[PUBLIC_PROFILES_KEY] = {
        profileId: {
          "defaultDisplayName": str,
          "defaultProfileImage": str,
          "posts": { postId: { ... } }
        }
      }

    Dépendances:
      state.data["emojiPresets"] : dict
      state.data["commentSets"]  : dict
    """

    def __init__(self, state: AppState):
        super().__init__()
        self.state = state

        # Ton dossier images
        self.social_img_dir = r"C:\Users\nicol\Desktop\Pentania Studio\The Elf Next Stream\img\pictures\Social"

        self._building_ui = False

        # Editors
        self._profile_editor = self._build_profile_editor()
        self._post_editor = self._build_post_editor()

        # Shell (2 colonnes visibles)
        self.shell = SocialEditorShell(
            profile_editor=self._profile_editor,
            post_editor=self._post_editor,
            texts=ShellTexts(
                profiles_title="Profiles",
                posts_title="Posts",
                profiles_placeholder="Add profile id (Enter) e.g. CatElf",
                posts_placeholder="Add post id (Enter) e.g. Morning_Cookie",
            ),
            enable_profiles_crud=True,
            enable_posts_crud=True,
            show_profiles_panel=True,
        )

        # --- Drag & drop interne pour réordonner les profils (uniquement software)
        self.shell.panel_profiles.list.setDragEnabled(True)
        self.shell.panel_profiles.list.setAcceptDrops(True)
        self.shell.panel_profiles.list.setDropIndicatorShown(True)
        self.shell.panel_profiles.list.setDefaultDropAction(Qt.MoveAction)
        self.shell.panel_profiles.list.setDragDropMode(QAbstractItemView.InternalMove)

        # Capte le ré-ordonnancement
        self.shell.panel_profiles.list.model().rowsMoved.connect(self._on_profiles_reordered)
            
        layout = QVBoxLayout(self)
        layout.addWidget(self.shell, 1)
    
        # Bind shell callbacks
        self.shell.set_bindings(
            list_profiles=self._list_profiles,
            list_posts=self._list_posts,
            on_profile_selected=self._on_profile_selected,
            on_post_selected=self._on_post_selected,
            on_add_profile=self._profile_add,
            on_rename_profile=self._profile_rename_from_typed,
            on_delete_profile=self._profile_delete,
            on_add_post=self._post_add,
            on_rename_post=self._post_rename_from_typed,
            on_delete_post=self._post_delete,
        )
        self.shell.panel_profiles.set_clipboard_handlers(
            pack=self._pack_profile,
            paste=self._paste_profile,
        )
        self.shell.panel_posts.set_clipboard_handlers(
            pack=self._pack_post,
            paste=self._paste_post,
        )


        # State wiring
        self.state.dataChanged.connect(self.reload_from_state)

        # Init
        self.reload_from_state()


    def _pack_profile(self) -> object | None:
        profile_id = self.shell.current_profile_id()
        if not profile_id:
            return None

        profiles = self._public_profiles()
        if profile_id not in profiles:
            return None

        return {
            "kind": "public_profile",
            "id": profile_id,
            "data": copy.deepcopy(profiles[profile_id]),
        }


    def _paste_profile(self, payload: object) -> bool:
        if not isinstance(payload, dict) or payload.get("kind") != "public_profile":
            return False

        profiles = self._public_profiles()

        base_id = str(payload.get("id") or "Profile").strip() or "Profile"
        data = payload.get("data")
        if not isinstance(data, dict):
            return False

        new_id = ListPanel.make_unique_name(base_id, exists=lambda s: s in profiles)
        new_data = copy.deepcopy(data)

        # order: append en fin
        self._rebuild_profile_orders()
        new_data["order"] = self.shell.panel_profiles.list.count()

        profiles[new_id] = new_data

        self.state.mark_dirty()

        with self._ui_guard():
            self.shell.reload_lists(preserve_selection=True)
            found = self.shell.panel_profiles.list.findItems(new_id, Qt.MatchExactly)
            if found:
                self.shell.panel_profiles.list.setCurrentItem(found[0])
                self.shell.panel_profiles.list.scrollToItem(found[0])

        return True

    def _pack_post(self) -> object | None:
        profile_id = self.shell.current_profile_id()
        post_id = self.shell.current_post_id()
        if not profile_id or not post_id:
            return None

        posts = self._profile_posts(profile_id)
        if post_id not in posts:
            return None

        return {
            "kind": "public_post",
            "id": post_id,
            "data": copy.deepcopy(posts[post_id]),
        }


    def _paste_post(self, payload: object) -> bool:
        if not isinstance(payload, dict) or payload.get("kind") != "public_post":
            return False

        profile_id = self.shell.current_profile_id()
        if not profile_id:
            return False

        posts = self._profile_posts(profile_id)

        base_id = str(payload.get("id") or "Post").strip() or "Post"
        data = payload.get("data")
        if not isinstance(data, dict):
            return False

        new_id = ListPanel.make_unique_name(base_id, exists=lambda s: s in posts)
        posts[new_id] = copy.deepcopy(data)

        self.state.mark_dirty()

        with self._ui_guard():
            self.shell.reload_lists(preserve_selection=True)
            found = self.shell.panel_posts.list.findItems(new_id, Qt.MatchExactly)
            if found:
                self.shell.panel_posts.list.setCurrentItem(found[0])
                self.shell.panel_posts.list.scrollToItem(found[0])

        return True


    # =========================================================
    # Guards / state helpers
    # =========================================================
    @contextmanager
    def _ui_guard(self):
        self._building_ui = True
        try:
            yield
        finally:
            self._building_ui = False

    def _ensure_public_root(self) -> dict[str, Any]:
        return self.state.data.setdefault(PUBLIC_PROFILES_KEY, {})

    def _public_profiles(self) -> dict[str, Any]:
        return self._ensure_public_root()

    def _get_profile(self, profile_id: str) -> dict[str, Any]:
        profiles = self._public_profiles()
        prof = profiles.setdefault(profile_id, {})
        prof.setdefault("defaultDisplayName", "")
        prof.setdefault("defaultProfileImage", "")
        prof.setdefault("posts", {})
        return prof

    def _profile_posts(self, profile_id: str) -> dict[str, Any]:
        return self._get_profile(profile_id).setdefault("posts", {})

    def _get_post(self, profile_id: str, post_id: str) -> dict[str, Any]:
        posts = self._profile_posts(profile_id)
        post = posts.setdefault(post_id, {})
        post.setdefault("pictureName", "")
        post.setdefault("description", "")
        post.setdefault("timeslot", "all")
        post.setdefault("conditionJS", "")
        post.setdefault("effectJs", "")
        post.setdefault("emojiPreset", "")      # "" => custom
        post.setdefault("emojiOverride", self._default_emoji())
        post.setdefault("commentsSet", "")
        post.setdefault("lewdCondition", {"min": 0, "max": 999999})
        return post

    def _default_emoji(self) -> dict[str, Any]:
        return {
            "up": {"min": 0, "max": 0},
            "down": {"min": 0, "max": 0},
            "heart": {"min": 0, "max": 0},
            "comment": {"min": 0, "max": 0},
        }

    def _emoji_presets(self) -> dict[str, Any]:
        return self.state.data.setdefault("emojiPresets", {})

    def _comment_sets(self) -> dict[str, Any]:
        return self.state.data.setdefault("commentSets", {})

    def _to_int(self, text: str, default: int = 0) -> int:
        try:
            return int(text) if str(text).strip() else default
        except ValueError:
            return default

    def _rebuild_profile_orders(self) -> None:
        """Réécrit profiles[pid]['order'] selon l'ordre visible dans la liste."""
        profiles = self._public_profiles()
        for i in range(self.shell.panel_profiles.list.count()):
            pid = self.shell.panel_profiles.list.item(i).text()
            if pid in profiles:
                profiles[pid]["order"] = i

    def _on_profiles_reordered(self, *_args) -> None:
        if self._building_ui:
            return
        self._rebuild_profile_orders()
        self.state.mark_dirty()

    # =========================================================
    # Shell bindings
    # =========================================================
    def _list_profiles(self) -> list[str]:
        profiles = self._public_profiles()
        return [
            pid for pid, _ in sorted(
                profiles.items(),
                key=lambda kv: self._to_int(kv[1].get("order", 0), 0),
            )
        ]


    def _list_posts(self, profile_id: str) -> list[str]:
        if not profile_id:
            return []
        return sorted(self._profile_posts(profile_id).keys())

    def _on_profile_selected(self, profile_id: str | None) -> None:
        self._refresh_profile_editor(profile_id)

        # Quand on change de profil, on n'a plus de post sélectionné "valide"
        self._refresh_post_editor(profile_id, None)

    def _on_post_selected(self, profile_id: str | None, post_id: str | None) -> None:
        self._refresh_post_editor(profile_id, post_id)

    # =========================================================
    # Build editors
    # =========================================================
    def _build_profile_editor(self) -> QWidget:
        w = QWidget()
        root = QVBoxLayout(w)

        grp = QGroupBox("Public Profile")
        grp.setMaximumWidth(720)
        form = QFormLayout(grp)

        self.lbl_profile_id = QLabel("-")
        self.lbl_profile_id.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.lbl_profile_id.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.lbl_profile_id.setStyleSheet("""
            QLabel{
                font-size: 20px;
                font-weight: 600;
                padding: 6px 8px;
            }
        """)
        
        self.le_display_name = QLineEdit()
        self.le_display_name.textEdited.connect(self._on_profile_changed)

        self.lbl_profile_img = ClickableImageLabel()
        self.lbl_profile_img.on_double_click = self._pick_profile_image

        # ─────────────────────────────────────────────────────────────
        # Header compact: image (≤ 200px) à gauche + displayName à droite
        # (sans labels "defaultDisplayName"/"defaultProfileImage")
        # ─────────────────────────────────────────────────────────────
        self.lbl_profile_img.setFixedSize(50, 50)

        header = QWidget()
        header_lay = QHBoxLayout(header)
        header_lay.setContentsMargins(0, 0, 0, 0)
        header_lay.setSpacing(12)

        header_lay.addWidget(self.lbl_profile_img, 0, Qt.AlignLeft | Qt.AlignTop)
        header_lay.addWidget(self.le_display_name, 1)

        form.addRow("", self.lbl_profile_id)
        form.addRow("", header)


        root.addStretch(1)
        root.addWidget(grp, 0, alignment=Qt.AlignHCenter | Qt.AlignTop)
        root.addStretch(2)
        return w


    def _build_post_editor(self) -> QWidget:
        w = QWidget()
        root = QVBoxLayout(w)

        self.grp_post = QGroupBox("")
        self.grp_post.setMaximumWidth(900)
        form = QFormLayout(self.grp_post)

        self.lbl_post_id = QLabel("-")
        self.lbl_post_id.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self.lbl_post_img = ClickableImageLabel()
        self.lbl_post_img.on_double_click = self._pick_post_image

        self.te_description = QTextEdit()
        self.te_description.textChanged.connect(self._on_post_description_changed)

        self.cb_timeslot = NoWheelComboBox()
        self.cb_timeslot.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.cb_timeslot.setMinimumContentsLength(10)   # réserve une largeur min (chars)
        self.cb_timeslot.setSizePolicy(self.cb_timeslot.sizePolicy().horizontalPolicy(), self.cb_timeslot.sizePolicy().verticalPolicy())
        self.cb_timeslot.addItems(list(TIME_SLOTS))
        self.cb_timeslot.currentIndexChanged.connect(self._on_post_simple_changed)

        self.le_lewd_min = QLineEdit()
        self.le_lewd_min.setValidator(QIntValidator(0, 999999, self))
        self.le_lewd_min.textEdited.connect(self._on_post_simple_changed)

        self.le_lewd_max = QLineEdit()
        self.le_lewd_max.setValidator(QIntValidator(0, 999999, self))
        self.le_lewd_max.textEdited.connect(self._on_post_simple_changed)

        row_lewd = QWidget()
        row_lewd_lay = QHBoxLayout(row_lewd)
        row_lewd_lay.setContentsMargins(0, 0, 0, 0)
        row_lewd_lay.setSpacing(8)

        row_lewd_lay.addWidget(QLabel("Min"))
        row_lewd_lay.addWidget(self.le_lewd_min)
        row_lewd_lay.addSpacing(16)
        row_lewd_lay.addWidget(QLabel("Max"))
        row_lewd_lay.addWidget(self.le_lewd_max)
        row_lewd_lay.addStretch(1)
        
        self.le_condition = QLineEdit()
        self.le_condition.textEdited.connect(self._on_post_simple_changed)

        self.le_effect = QLineEdit()
        self.le_effect.textEdited.connect(self._on_post_simple_changed)
        
        self.le_condition.setToolTip(HELP_CONDITION_JS)
        self.le_effect.setToolTip(HELP_EFFECT_JS)

        # Optionnel: tooltip plus long (ms). -1 => reste jusqu'à quitter
        self.le_condition.setToolTipDuration(-1)
        self.le_effect.setToolTipDuration(-1)
        # =========================================================
        # Emoji (compact)
        # =========================================================
        grp_emoji = QGroupBox("Emoji")
        grp_emoji.setMaximumWidth(520)  # compact visuel (ajuste si besoin)
        emoji_layout = QVBoxLayout(grp_emoji)
        emoji_layout.setContentsMargins(8, 8, 8, 8)
        emoji_layout.setSpacing(6)

        # (Optionnel) Preset en haut (petit "plus")
        row_preset = QHBoxLayout()
        row_preset.setSpacing(6)

        self.cb_emoji_preset = NoWheelComboBox()
        self.cb_emoji_preset.setMinimumWidth(240)
        self.cb_emoji_preset.currentIndexChanged.connect(self._on_emoji_preset_selected)

        self.btn_emoji_reset = QPushButton("Reset")
        self.btn_emoji_reset.setFixedWidth(80)
        self.btn_emoji_reset.clicked.connect(self._emoji_reset_custom)

        row_preset.addWidget(QLabel("Preset"))
        row_preset.addWidget(self.cb_emoji_preset, 1)
        row_preset.addWidget(self.btn_emoji_reset)

        emoji_layout.addLayout(row_preset)

        # ✅ Grille compacte (QLineEdit au lieu de QSpinBox)
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        grid.setContentsMargins(0, 0, 0, 0)

        # Validator numérique (0..999999)
        self._emoji_int_validator = QIntValidator(0, 999999, self)

        # Stocke les inputs: (key,"min"/"max") -> QLineEdit
        self.emoji_inputs: dict[tuple[str, str], QLineEdit] = {}

        cells = [
            ("up", 0, 0, "👍 Like"),
            ("down", 0, 1, "👎 Dislike"),
            ("heart", 1, 0, "❤️ Love"),
            ("comment", 1, 1, "💬 Comment"),
        ]

        def _make_int_le() -> QLineEdit:
            le = QLineEdit()
            le.setValidator(self._emoji_int_validator)
            le.setFixedWidth(64)          # encore plus compact
            le.setAlignment(Qt.AlignCenter)
            le.setFrame(False)
            return le

        for key, r, c, icon in cells:
            frame = QFrame()
            frame.setFrameShape(QFrame.NoFrame)
            frame.setStyleSheet("QFrame{border:1px solid #444;border-radius:6px;padding:6px;}")

            cell_layout = QVBoxLayout(frame)
            cell_layout.setContentsMargins(4, 4, 4, 4)
            cell_layout.setSpacing(4)

            lbl = QLabel(icon)
            lbl.setAlignment(Qt.AlignHCenter)
            lbl.setStyleSheet("QLabel{border:none;background:transparent;padding:0px 4px;}")
            cell_layout.addWidget(lbl)

            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(6)
            row.setAlignment(Qt.AlignHCenter)

            le_min = _make_int_le()
            le_max = _make_int_le()
            self.emoji_inputs[(key, "min")] = le_min
            self.emoji_inputs[(key, "max")] = le_max

            # Toute modif => détache preset + save override
            le_min.textEdited.connect(lambda _t, k=key: self._on_emoji_value_changed(k))
            le_max.textEdited.connect(lambda _t, k=key: self._on_emoji_value_changed(k))

            row.addStretch(1)

            row.addWidget(le_min)

            lbl_to = QLabel("to")
            lbl_to.setStyleSheet("QLabel{border:none;background:transparent;padding:0px 6px;}")
            row.addWidget(lbl_to)

            row.addWidget(le_max)

            row.addStretch(1)


            cell_layout.addLayout(row)
            grid.addWidget(frame, r, c)

        emoji_layout.addLayout(grid)


        # Comment set dropdown
        self.cb_comment_set = NoWheelComboBox()
        self.cb_comment_set.currentIndexChanged.connect(self._on_post_simple_changed)

        # =========================================================
        # Header: image à gauche (collée), PostID centré + timeSlot sur 2 lignes
        # =========================================================
        header = QWidget()
        h = QHBoxLayout(header)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(20)  # ✅ écart demandé

        # Image (pictureName) - collée à gauche
        self.lbl_post_img.setFixedSize(220, 220)
        h.addWidget(self.lbl_post_img, 0, alignment=Qt.AlignLeft | Qt.AlignTop)

        # Colonne droite dans un widget (pour pouvoir lui donner une minWidth propre)
        right_widget = QWidget()
        right_col = QVBoxLayout(right_widget)
        right_col.setContentsMargins(0, 0, 0, 0)
        right_col.setSpacing(10)

        # Post ID (gros + centré)
        self.lbl_post_id.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.lbl_post_id.setStyleSheet("""
            QLabel{
                font-size: 20px;
                font-weight: 600;
                padding: 6px 8px;
            }
        """)

        right_col.addWidget(self.lbl_post_id, 0, alignment=Qt.AlignHCenter)

        # timeSlot en 2 lignes : label puis dropdown
        lbl_slot = QLabel("timeSlot")
        lbl_slot.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        lbl_slot.setStyleSheet("QLabel{font-weight:600; padding-top:4px;}")

        self.cb_timeslot.setMinimumWidth(220)  # ✅ évite le 'morn' tronqué

        right_col.addWidget(lbl_slot, 0, alignment=Qt.AlignHCenter)
        right_col.addWidget(self.cb_timeslot, 0, alignment=Qt.AlignHCenter)

        # Un peu d'air en bas pour occuper la hauteur restante
        right_col.addStretch(1)

        # Le widget droit prend toute la place restante
        h.addWidget(right_widget, 1)

        # On met tout ça dans le form en une seule "row"
        form.addRow("", header)


        form.addRow("description", self.te_description)
        form.addRow("lewdCondition", row_lewd)
        form.addRow("conditionJS", self.le_condition)
        form.addRow("effectJs", self.le_effect)
        form.addRow(grp_emoji)
        form.addRow("comments (Set)", self.cb_comment_set)

        root.addStretch(1)
        root.addWidget(self.grp_post, 0, alignment=Qt.AlignHCenter | Qt.AlignTop)
        root.addStretch(2)
        return w


    # =========================================================
    # Reload / refresh
    # =========================================================
    def _ensure_profile_orders(self) -> None:
        profiles = self._public_profiles()
        # Si aucun order, on initialise selon tri alpha actuel pour rester stable.
        missing = [pid for pid, p in profiles.items() if "order" not in p]
        if not missing:
            return

        for i, pid in enumerate(sorted(profiles.keys())):
            profiles.setdefault(pid, {})["order"] = i

    def reload_from_state(self) -> None:
        with self._ui_guard():
            self._ensure_public_root()
            self._ensure_profile_orders()
            self.shell.reload_lists(preserve_selection=True)
            ...


            self._refresh_emoji_preset_dropdown()
            self._refresh_comment_set_dropdown()

            prof = self.shell.current_profile_id()
            post = self.shell.current_post_id()

            self._refresh_profile_editor(prof)
            self._refresh_post_editor(prof, post)

    def _refresh_profile_editor(self, profile_id: str | None) -> None:
        enabled = bool(profile_id)
        # On disable l'éditeur profil si rien sélectionné
        self._profile_editor.setEnabled(enabled)

        if not enabled:
            with self._ui_guard():
                self.lbl_profile_id.setText("-")
                self.le_display_name.setText("")
                self._set_image_preview(self.lbl_profile_img, "")
            return

        prof = self._get_profile(profile_id)

        with self._ui_guard():
            self.lbl_profile_id.setText(profile_id)
            self.le_display_name.setText(prof.get("defaultDisplayName", "") or "")
            self._set_image_preview(self.lbl_profile_img, prof.get("defaultProfileImage", "") or "")

    def _refresh_post_editor(self, profile_id: str | None, post_id: str | None) -> None:
        enabled = bool(profile_id) and bool(post_id)
        self.grp_post.setEnabled(enabled)

        if not enabled:
            with self._ui_guard():
                self.lbl_post_id.setText("-")
                self._set_image_preview(self.lbl_post_img, "")
                self.te_description.setPlainText("")
                self.cb_timeslot.setCurrentText("all")
                self.le_condition.setText("")
                self.le_effect.setText("")
                self._select_emoji_preset("")
                self._set_emoji_values(self._default_emoji())
                self._select_comment_set("")
            return

        post = self._get_post(profile_id, post_id)

        with self._ui_guard():
            self.lbl_post_id.setText(post_id)
            self._set_image_preview(self.lbl_post_img, post.get("pictureName", "") or "")

            self.te_description.setPlainText(post.get("description", "") or "")
            self.cb_timeslot.setCurrentText(post.get("timeslot", "all") or "all")
            self.le_condition.setText(post.get("conditionJS", "") or "")
            self.le_effect.setText(post.get("effectJs", "") or "")

            preset = (post.get("emojiPreset") or "").strip()
            if preset and preset in self._emoji_presets():
                self._select_emoji_preset(preset)
                self._set_emoji_values(self._emoji_presets()[preset])
            else:
                self._select_emoji_preset("")
                self._set_emoji_values(post.get("emojiOverride") or self._default_emoji())

            self._select_comment_set(post.get("commentsSet", "") or "")

    def _refresh_emoji_preset_dropdown(self) -> None:
        presets = sorted(self._emoji_presets().keys())
        with QSignalBlocker(self.cb_emoji_preset):
            self.cb_emoji_preset.clear()
            self.cb_emoji_preset.addItem("(custom)")
            for p in presets:
                self.cb_emoji_preset.addItem(p)

    def _refresh_comment_set_dropdown(self) -> None:
        sets = sorted(self._comment_sets().keys())
        with QSignalBlocker(self.cb_comment_set):
            self.cb_comment_set.clear()
            self.cb_comment_set.addItem("")
            for s in sets:
                self.cb_comment_set.addItem(s)

    # =========================================================
    # Image preview + pickers
    # =========================================================
    def _set_image_preview(self, label: ClickableImageLabel, relpath: str) -> None:
        relpath = (relpath or "").strip().replace("\\", "/")
        if not relpath:
            label.setPixmap(QPixmap())
            label.setText("Double-clic pour choisir\nune image")
            return

        path = relpath
        if not os.path.isabs(path):
            path = os.path.join(self.social_img_dir, relpath.replace("/", os.sep))

        if not os.path.exists(path):
            label.setPixmap(QPixmap())
            label.setText(f"Image introuvable:\n{relpath}\n\n(double-clic pour choisir)")
            return

        pix = QPixmap(path)
        if pix.isNull():
            label.setPixmap(QPixmap())
            label.setText(f"Impossible de lire:\n{relpath}\n\n(double-clic)")
            return

        label.setText("")
        label.set_original_pixmap(pix)

    def _pick_image_relpath(self, *, start_subdir: str = "") -> str | None:
        base_dir = self.social_img_dir
        start_dir = os.path.join(base_dir, start_subdir) if start_subdir else base_dir
        if not os.path.isdir(start_dir):
            start_dir = base_dir if os.path.isdir(base_dir) else os.getcwd()

        file_path, _filter = QFileDialog.getOpenFileName(
            self,
            "Choisir une image",
            start_dir,
            "Images (*.png *.jpg *.jpeg *.webp);;Tous (*.*)"
        )
        if not file_path:
            return None

        try:
            rel = os.path.relpath(file_path, base_dir)
        except ValueError:
            rel = os.path.basename(file_path)

        return rel.replace("\\", "/")

    def _pick_profile_image(self) -> None:
        profile_id = self.shell.current_profile_id()
        if not profile_id:
            return

        # Dossier conseillé: Social/Profile/Public/...
        rel = self._pick_image_relpath(start_subdir="Profile")
        if not rel:
            return

        prof = self._get_profile(profile_id)
        prof["defaultProfileImage"] = rel
        self.state.mark_dirty()
        self._set_image_preview(self.lbl_profile_img, rel)

    def _pick_post_image(self) -> None:
        profile_id = self.shell.current_profile_id()
        post_id = self.shell.current_post_id()
        if not profile_id or not post_id:
            return

        # Dossier conseillé: Social/Picture/Public/<profileId>/...
        # Si le dossier n'existe pas, le file dialog retombe sur Social.
        rel = self._pick_image_relpath(start_subdir=f"Picture/{profile_id}")
        if not rel:
            return

        post = self._get_post(profile_id, post_id)
        post["pictureName"] = rel
        self.state.mark_dirty()
        self._set_image_preview(self.lbl_post_img, rel)

    # =========================================================
    # Profile changes
    # =========================================================
    def _on_profile_changed(self, _text: str) -> None:
        if self._building_ui:
            return
        profile_id = self.shell.current_profile_id()
        if not profile_id:
            return
        prof = self._get_profile(profile_id)
        prof["defaultDisplayName"] = self.le_display_name.text()
        self.state.mark_dirty()

    # =========================================================
    # Profiles CRUD
    # =========================================================
    def _profile_add(self, profile_id: str) -> None:
        profile_id = profile_id.strip()
        if not profile_id:
            return

        profiles = self._public_profiles()
        if profile_id in profiles:
            QMessageBox.warning(self, "Erreur", "Ce profil existe déjà.")
            return

        # s'aligne sur l'ordre visible actuel
        self._rebuild_profile_orders()

        prof = self._get_profile(profile_id)
        prof["order"] = self.shell.panel_profiles.list.count()

        self.state.mark_dirty()
        self.shell.panel_profiles.clear_input()


        with self._ui_guard():
            self.shell.reload_lists(preserve_selection=True)
            found = self.shell.panel_profiles.list.findItems(profile_id, Qt.MatchExactly)
            if found:
                self.shell.panel_profiles.list.setCurrentItem(found[0])

    def goto_post(self, profile_id: str, post_key: str, field: str = "") -> None:
        with self._ui_guard():
            self._refresh_profiles(preserve_selection=True)
            p_items = self.panel_profiles.list.findItems(profile_id, Qt.MatchExactly)
            if p_items:
                self.panel_profiles.list.setCurrentItem(p_items[0])
                self.panel_profiles.list.scrollToItem(p_items[0])

            self._refresh_posts()
            post_items = self.panel_posts.list.findItems(post_key, Qt.MatchExactly)
            if post_items:
                self.panel_posts.list.setCurrentItem(post_items[0])
                self.panel_posts.list.scrollToItem(post_items[0])

            # Optionnel : si tu as un widget spécifique pour emojiPreset/commentsSet, focus dessus.
            # if field == "emojiPreset": self.combo_emojiPreset.setFocus()
            # if field == "commentsSet": self.combo_commentsSet.setFocus()


    def _profile_rename_from_typed(self, typed: str) -> None:
        old = self.shell.current_profile_id()
        if not old:
            return

        if not typed.strip():
            self.shell.panel_profiles.input.setText(old)
            self.shell.panel_profiles.focus_input(select_all=True)
            return

        self._profile_rename(old, typed.strip())

    def _profile_rename(self, old: str, new: str) -> None:
        profiles = self._public_profiles()
        if new == old:
            self.shell.panel_profiles.clear_input()
            return
        if new in profiles:
            QMessageBox.warning(self, "Erreur", f"Le profil '{new}' existe déjà.")
            return

        profiles[new] = profiles.pop(old)
        self.state.mark_dirty()
        self.shell.panel_profiles.clear_input()

        with self._ui_guard():
            self.shell.reload_lists(preserve_selection=True)
            found = self.shell.panel_profiles.list.findItems(new, Qt.MatchExactly)
            if found:
                self.shell.panel_profiles.list.setCurrentItem(found[0])

    def _profile_delete(self) -> None:
        profile_id = self.shell.current_profile_id()
        if not profile_id:
            return

        # ListPanel fait déjà la confirmation
        self._public_profiles().pop(profile_id, None)
        self.state.mark_dirty()

        with self._ui_guard():
            self.shell.reload_lists(preserve_selection=True)
            prof = self.shell.current_profile_id()
            post = self.shell.current_post_id()
            self._refresh_profile_editor(prof)
            self._refresh_post_editor(prof, post)

    # =========================================================
    # Posts CRUD
    # =========================================================
    def _post_add(self, post_id: str) -> None:
        profile_id = self.shell.current_profile_id()
        if not profile_id:
            return

        post_id = post_id.strip()
        if not post_id:
            return

        posts = self._profile_posts(profile_id)
        if post_id in posts:
            QMessageBox.warning(self, "Erreur", f"Le post '{post_id}' existe déjà.")
            return

        posts[post_id] = {
            "pictureName": "",
            "description": "",
            "timeslot": "all",
            "conditionJS": "",
            "effectJs": "",
            "emojiPreset": "",
            "emojiOverride": self._default_emoji(),
            "commentsSet": "",
            "lewdCondition": {"min": 0, "max": 999999}
        }

        self.state.mark_dirty()
        self.shell.panel_posts.clear_input()

        with self._ui_guard():
            self.shell.reload_lists(preserve_selection=True)
            found = self.shell.panel_posts.list.findItems(post_id, Qt.MatchExactly)
            if found:
                self.shell.panel_posts.list.setCurrentItem(found[0])

    def _post_rename_from_typed(self, typed: str) -> None:
        profile_id = self.shell.current_profile_id()
        old = self.shell.current_post_id()
        if not profile_id or not old:
            return

        if not typed.strip():
            self.shell.panel_posts.input.setText(old)
            self.shell.panel_posts.focus_input(select_all=True)
            return

        self._post_rename(profile_id, old, typed.strip())

    def _post_rename(self, profile_id: str, old: str, new: str) -> None:
        posts = self._profile_posts(profile_id)
        if new == old:
            self.shell.panel_posts.clear_input()
            return
        if new in posts:
            QMessageBox.warning(self, "Erreur", f"Le post '{new}' existe déjà.")
            return

        posts[new] = posts.pop(old)
        self.state.mark_dirty()
        self.shell.panel_posts.clear_input()

        with self._ui_guard():
            self.shell.reload_lists(preserve_selection=True)
            found = self.shell.panel_posts.list.findItems(new, Qt.MatchExactly)
            if found:
                self.shell.panel_posts.list.setCurrentItem(found[0])

    def _post_delete(self) -> None:
        profile_id = self.shell.current_profile_id()
        post_id = self.shell.current_post_id()
        if not profile_id or not post_id:
            return

        self._profile_posts(profile_id).pop(post_id, None)
        self.state.mark_dirty()

        with self._ui_guard():
            self.shell.reload_lists(preserve_selection=True)
            self._refresh_post_editor(self.shell.current_profile_id(), self.shell.current_post_id())

    # =========================================================
    # Post field changes
    # =========================================================
    def _on_post_description_changed(self) -> None:
        if self._building_ui:
            return
        profile_id = self.shell.current_profile_id()
        post_id = self.shell.current_post_id()
        if not profile_id or not post_id:
            return
        post = self._get_post(profile_id, post_id)
        post["description"] = self.te_description.toPlainText()
        self.state.mark_dirty()

    def _on_post_simple_changed(self, *_args) -> None:
        if self._building_ui:
            return
        profile_id = self.shell.current_profile_id()
        post_id = self.shell.current_post_id()
        if not profile_id or not post_id:
            return

        post = self._get_post(profile_id, post_id)
        post["timeslot"] = self.cb_timeslot.currentText()
        post["conditionJS"] = self.le_condition.text()
        post["effectJs"] = self.le_effect.text()
        post["commentsSet"] = self.cb_comment_set.currentText()
        self.state.mark_dirty()

    # =========================================================
    # Emoji preset logic (detach on edit)
    # =========================================================
    def _select_emoji_preset(self, preset: str) -> None:
        with QSignalBlocker(self.cb_emoji_preset):
            if not preset:
                self.cb_emoji_preset.setCurrentIndex(0)
                return
            idx = self.cb_emoji_preset.findText(preset)
            self.cb_emoji_preset.setCurrentIndex(idx if idx >= 0 else 0)

    def _set_emoji_values(self, data: dict[str, Any]) -> None:
        with self._ui_guard():
            for key in ("up", "down", "heart", "comment"):
                vmin = int(data.get(key, {}).get("min", 0))
                vmax = int(data.get(key, {}).get("max", 0))
                if vmin > vmax:
                    vmax = vmin
                self.emoji_inputs[(key, "min")].setText(str(vmin))
                self.emoji_inputs[(key, "max")].setText(str(vmax))

    def _emoji_current_override_from_ui(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key in ("up", "down", "heart", "comment"):
            tmin = (self.emoji_inputs[(key, "min")].text() or "").strip()
            tmax = (self.emoji_inputs[(key, "max")].text() or "").strip()

            vmin = int(tmin) if tmin.isdigit() else 0
            vmax = int(tmax) if tmax.isdigit() else 0
            if vmin > vmax:
                vmax = vmin
            out[key] = {"min": vmin, "max": vmax}
        return out

    def _on_emoji_preset_selected(self, _index: int) -> None:
        if self._building_ui:
            return
        profile_id = self.shell.current_profile_id()
        post_id = self.shell.current_post_id()
        if not profile_id or not post_id:
            return

        post = self._get_post(profile_id, post_id)
        chosen = self.cb_emoji_preset.currentText()

        if chosen == "(custom)":
            post["emojiPreset"] = ""
            post["emojiOverride"] = self._emoji_current_override_from_ui()
            self.state.mark_dirty()
            return

        presets = self._emoji_presets()
        if chosen in presets:
            post["emojiPreset"] = chosen
            post["emojiOverride"] = presets[chosen]
            with self._ui_guard():
                self._set_emoji_values(presets[chosen])
            self.state.mark_dirty()

    def _on_emoji_value_changed(self, key: str) -> None:
        if self._building_ui:
            return
        profile_id = self.shell.current_profile_id()
        post_id = self.shell.current_post_id()
        if not profile_id or not post_id:
            return

        post = self._get_post(profile_id, post_id)

        le_min = self.emoji_inputs[(key, "min")]
        le_max = self.emoji_inputs[(key, "max")]

        tmin = (le_min.text() or "").strip()
        tmax = (le_max.text() or "").strip()

        vmin = int(tmin) if tmin.isdigit() else 0
        vmax = int(tmax) if tmax.isdigit() else 0

        if vmin > vmax:
            with self._ui_guard():
                le_max.setText(str(vmin))

        preset = (post.get("emojiPreset") or "").strip()
        if preset:
            post["emojiPreset"] = ""
            with self._ui_guard():
                self._select_emoji_preset("")

        post["emojiOverride"] = self._emoji_current_override_from_ui()
        self.state.mark_dirty()

    def _emoji_reset_custom(self) -> None:
        profile_id = self.shell.current_profile_id()
        post_id = self.shell.current_post_id()
        if not profile_id or not post_id:
            return
        post = self._get_post(profile_id, post_id)
        post["emojiPreset"] = ""
        post["emojiOverride"] = self._default_emoji()
        with self._ui_guard():
            self._select_emoji_preset("")
            self._set_emoji_values(post["emojiOverride"])
        self.state.mark_dirty()

    # =========================================================
    # Comment set selection
    # =========================================================
    def _select_comment_set(self, set_id: str) -> None:
        with QSignalBlocker(self.cb_comment_set):
            idx = self.cb_comment_set.findText(set_id)
            self.cb_comment_set.setCurrentIndex(idx if idx >= 0 else 0)


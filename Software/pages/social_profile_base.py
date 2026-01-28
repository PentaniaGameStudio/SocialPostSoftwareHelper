from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any

from PySide6.QtCore import Qt, QSignalBlocker
from PySide6.QtGui import QPixmap, QIntValidator
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QGroupBox,
    QLabel, QLineEdit, QTextEdit, QComboBox, QPushButton, QFrame,
    QHBoxLayout, QGridLayout, QSizePolicy
)

from state import AppState
from social_editor_shell import HELP_EFFECT_JS, HELP_CONDITION_JS, TIME_SLOTS
from ui_helpers import NoWheelComboBox, ClickableImageLabel

# ============================================================
# PARAMÈTRES UI (modifiables facilement)
# ============================================================

# Largeurs max des blocs
PROFILE_EDITOR_MAX_WIDTH = 1200
POST_EDITOR_MAX_WIDTH = 1200          # ✅ largeur globale du bloc post (conteneur)

# Image sizes
PROFILE_IMAGE_SIZE = 50
POST_IMAGE_SIZE = 220

# Spacing / margins
HEADER_HSPACING = 20                 # espace entre image et colonne droite
HEADER_MARGINS = (0, 0, 0, 0)         # (left, top, right, bottom)
POST_FORM_SPACING = 10               # spacing interne du form (vertical)

# Description sizing
DESCRIPTION_SAMPLE = "Sometimes the world is loud, so I hide in other worlds instead"
DESCRIPTION_MIN_EXTRA_PX = 24
DESCRIPTION_LINES = 8                # hauteur approx en lignes
DESCRIPTION_MIN_WIDTH = 260

# Emoji block
EMOJI_MAX_WIDTH = 520

# Dropdown sizes
TIMESLOT_MIN_WIDTH = 220
EMOJI_PRESET_MIN_WIDTH = 240
RESET_BTN_WIDTH = 80

# Validators
INT_MAX = 999999


class SocialProfilePageBase(QWidget):
    PROFILE_GROUP_TITLE = "Profile"
    USES_PROFILE_SCOPE_FOR_POST = False

    def __init__(self, state: AppState):
        super().__init__()
        self.state = state

        # Ton dossier images
        self.social_img_dir = r"C:\Users\nicol\Desktop\Pentania Studio\The Elf Next Stream\img\pictures\Social"

        self._building_ui = False

        # Editors
        self._profile_editor = self._build_profile_editor()
        self._post_editor = self._build_post_editor()

    @contextmanager
    def _ui_guard(self):
        self._building_ui = True
        try:
            yield
        finally:
            self._building_ui = False

    # =========================================================
    # Abstract-ish hooks
    # =========================================================
    def _current_profile_id(self) -> str | None:
        raise NotImplementedError

    def _current_post_id(self) -> str | None:
        raise NotImplementedError

    def _get_profile_data(self, profile_id: str) -> dict[str, Any]:
        raise NotImplementedError

    def _get_post_data(self, profile_id: str | None, post_id: str) -> dict[str, Any]:
        raise NotImplementedError

    def _post_image_subdir(self, profile_id: str | None) -> str:
        raise NotImplementedError

    # =========================================================
    # Shared helpers
    # =========================================================
    def _current_profile_context(self) -> dict[str, Any] | None:
        profile_id = self._current_profile_id()
        if not profile_id:
            return None
        return self._get_profile_data(profile_id)

    def _current_post_context(self) -> dict[str, Any] | None:
        profile_id = self._current_profile_id()
        post_id = self._current_post_id()
        if not post_id:
            return None
        if self.USES_PROFILE_SCOPE_FOR_POST and not profile_id:
            return None
        return self._get_post_data(profile_id, post_id)

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

    # =========================================================
    # Build editors (shared)
    # =========================================================
    def _build_profile_editor(self) -> QWidget:
        w = QWidget()
        root = QVBoxLayout(w)

        grp = QGroupBox(self.PROFILE_GROUP_TITLE)
        grp.setMaximumWidth(PROFILE_EDITOR_MAX_WIDTH)
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
        self.lbl_profile_img.setFixedSize(PROFILE_IMAGE_SIZE, PROFILE_IMAGE_SIZE)

        header = QWidget()
        header.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
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
        w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        root.setContentsMargins(0, 0, 0, 0)

        self.grp_post = QGroupBox("")
        self.grp_post.setMaximumWidth(POST_EDITOR_MAX_WIDTH)
        self.grp_post.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        form = QFormLayout(self.grp_post)
        form.setFormAlignment(Qt.AlignHCenter | Qt.AlignTop)          # centre le contenu du form
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)       # labels alignés proprement
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)    # les champs grandissent
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)


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

        self.le_condition.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.le_effect.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        # Optionnel: tooltip plus long (ms). -1 => reste jusqu'à quitter
        self.le_condition.setToolTipDuration(-1)
        self.le_effect.setToolTipDuration(-1)
        # =========================================================
        # Emoji (compact)
        # =========================================================
        grp_emoji = QGroupBox("Emoji")
        grp_emoji.setMaximumWidth(EMOJI_MAX_WIDTH)
        emoji_layout = QVBoxLayout(grp_emoji)
        emoji_layout.setContentsMargins(8, 8, 8, 8)
        emoji_layout.setSpacing(6)

        # (Optionnel) Preset en haut (petit "plus")
        row_preset = QHBoxLayout()
        row_preset.setSpacing(6)

        self.cb_emoji_preset = NoWheelComboBox()
        self.cb_emoji_preset.setMinimumWidth(EMOJI_PRESET_MIN_WIDTH)
        self.cb_emoji_preset.currentIndexChanged.connect(self._on_emoji_preset_selected)

        self.btn_emoji_reset = QPushButton("Reset")
        self.btn_emoji_reset.setFixedWidth(RESET_BTN_WIDTH)
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
        self._emoji_int_validator = QIntValidator(0, INT_MAX, self)

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

        self.cb_comment_set.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        
        # =========================================================
        # Header: image à gauche (collée), PostID centré + timeSlot + description
        # =========================================================
        header = QWidget()
        header.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        h = QHBoxLayout(header)
        h.setContentsMargins(*HEADER_MARGINS)
        h.setSpacing(HEADER_HSPACING)
        
        self.lbl_post_img.setFixedSize(POST_IMAGE_SIZE, POST_IMAGE_SIZE)
        self.lbl_post_img.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)


        # Colonne droite
        right_widget = QWidget()
        right_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
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

        self.cb_timeslot.setMinimumWidth(TIMESLOT_MIN_WIDTH)  # ✅ évite le 'morn' tronqué
        right_col.addWidget(self.cb_timeslot, 0, alignment=Qt.AlignCenter)


        # La description doit s'étirer dans la largeur du bloc Post
        self.te_description.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.te_description.setMinimumWidth(DESCRIPTION_MIN_WIDTH )
        line_height = self.te_description.fontMetrics().lineSpacing()
        self.te_description.setFixedHeight(line_height * DESCRIPTION_LINES + 12)
        right_col.addWidget(self.te_description)

        # Un peu d'air en bas pour occuper la hauteur restante
        right_col.addStretch(1)

        h.addWidget(self.lbl_post_img, 0, Qt.AlignLeft | Qt.AlignTop)
        h.setSpacing(20)
        h.addWidget(right_widget, 1)

        # On met tout ça dans le form en une seule "row"
        form.addRow(header)

        form.addRow("Lewd Condition", self._center(row_lewd))
        form.addRow("Condition (JS)", self.le_condition)
        form.addRow("Effect (Js)", self.le_effect)
        form.addRow("Comments (Set)", self.cb_comment_set)
        form.addRow("", self._center(grp_emoji))                       # row full-width déjà, donc nickel

        root.addStretch(1)
        wrapper = QWidget()
        wrapper.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        wl = QHBoxLayout(wrapper)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.addStretch(1)
        wl.addWidget(self.grp_post)
        wl.addStretch(1)

        root.addWidget(wrapper)
        root.addStretch(2)
        return w

    def _center(self, widget: QWidget) -> QWidget:
        """Retourne un widget wrapper qui centre 'widget' horizontalement."""
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addStretch(1)
        lay.addWidget(widget, 0)
        lay.addStretch(1)
        return w
        
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
        return ClickableImageLabel.pick_image_relpath(
            self,
            base_dir=self.social_img_dir,
            start_subdir=start_subdir,
            settings_key="last_image_dir_social"
        )

    def _pick_profile_image(self) -> None:
        profile_id = self._current_profile_id()
        if not profile_id:
            return

        # Dossier conseillé: Social/Profile/...
        rel = self._pick_image_relpath(start_subdir="Profile")
        if not rel:
            return

        prof = self._get_profile_data(profile_id)
        prof["defaultProfileImage"] = rel
        self.state.mark_dirty()
        self._set_image_preview(self.lbl_profile_img, rel)

    def _pick_post_image(self) -> None:
        profile_id = self._current_profile_id()
        post_id = self._current_post_id()
        if not post_id:
            return
        if self.USES_PROFILE_SCOPE_FOR_POST and not profile_id:
            return

        rel = self._pick_image_relpath(start_subdir=self._post_image_subdir(profile_id))
        if not rel:
            return

        post = self._get_post_data(profile_id, post_id)
        post["pictureName"] = rel
        self.state.mark_dirty()
        self._set_image_preview(self.lbl_post_img, rel)

    # =========================================================
    # Profile changes
    # =========================================================
    def _on_profile_changed(self, _text: str) -> None:
        if self._building_ui:
            return
        prof = self._current_profile_context()
        if not prof:
            return
        prof["defaultDisplayName"] = self.le_display_name.text()
        self.state.mark_dirty()

    # =========================================================
    # Post field changes
    # =========================================================
    def _on_post_description_changed(self) -> None:
        if self._building_ui:
            return
        post = self._current_post_context()
        if not post:
            return
        post["description"] = self.te_description.toPlainText()
        self.state.mark_dirty()

    def _on_post_simple_changed(self, *_args) -> None:
        if self._building_ui:
            return
        post = self._current_post_context()
        if not post:
            return

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
        post = self._current_post_context()
        if not post:
            return

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

    def _on_emoji_value_changed(self, _key: str) -> None:
        if self._building_ui:
            return

        post = self._current_post_context()
        if not post:
            return

        # Récupère le post
        chosen = self.cb_emoji_preset.currentText()
        if chosen == "(custom)":
            post["emojiOverride"] = self._emoji_current_override_from_ui()
            post["emojiPreset"] = ""
        else:
            # Si on modifie manuellement, on repasse en custom
            post["emojiOverride"] = self._emoji_current_override_from_ui()
            post["emojiPreset"] = ""
            with self._ui_guard():
                self._select_emoji_preset("")

        self.state.mark_dirty()

    def _emoji_reset_custom(self) -> None:
        post = self._current_post_context()
        if not post:
            return

        post["emojiPreset"] = ""
        post["emojiOverride"] = self._default_emoji()
        with self._ui_guard():
            self._select_emoji_preset("")
            self._set_emoji_values(self._default_emoji())
        self.state.mark_dirty()

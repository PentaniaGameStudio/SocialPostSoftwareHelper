from __future__ import annotations

from typing import Callable
import json

from PySide6.QtCore import ( Qt, Signal, QEvent, QMimeData )
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QListWidget, QPushButton, QLineEdit,
    QAbstractItemView, QMessageBox, QInputDialog,
    QApplication, QComboBox, QLabel
)
from PySide6.QtGui import QKeySequence, QKeyEvent, QShortcut
from PySide6.QtCore import QSettings
from pathlib import Path

class AppSettings:
    """
    Gestion des settings persistants de l'app
    """
    _settings = QSettings("Unifox", "SocialPostEditor")

    @classmethod
    def get_last_image_dir(cls) -> Path | None:
        val = cls._settings.value("last_image_dir", "")
        return Path(val) if val else None

    @classmethod
    def set_last_image_dir(cls, path: Path) -> None:
        cls._settings.setValue("last_image_dir", str(path))
        
class ListPanel(QWidget):
    addRequested = Signal(str)
    editRequested = Signal(str)
    deleteRequested = Signal()
    selectionChanged = Signal()
    rowsMoved = Signal()
    MIME = "application/x-nas-listpanel+json"

    def __init__(
        self,
        *,
        placeholder: str,
        edit_label: str = "Edit",
        delete_label: str = "Delete",
        enable_reorder: bool = False,

        # Nouveau: confirmation delete
        confirm_delete: bool = True,
        confirm_delete_title: str = "Supprimer",
        confirm_delete_text: str = "Supprimer l'élément sélectionné ?",
        confirm_delete_builder: Callable[[str | None], str] | None = None,

        parent: QWidget | None = None
    ):
        super().__init__(parent)
        self._debug_clipboard = True  # Mets True pour voir les logs


        self._confirm_delete = confirm_delete
        self._confirm_delete_title = confirm_delete_title
        self._confirm_delete_text = confirm_delete_text
        self._confirm_delete_builder = confirm_delete_builder

        self.list = QListWidget()
        self.list.installEventFilter(self)
        self.list.viewport().installEventFilter(self)
        self.list.setFocusPolicy(Qt.StrongFocus)
        
        self._clipboard_pack_fn = None
        self._clipboard_paste_fn = None
        
        self._sc_copy = QShortcut(QKeySequence.Copy, self)
        self._sc_copy.setContext(Qt.WidgetWithChildrenShortcut)
        self._sc_copy.activated.connect(self._on_copy)
        
        self._sc_paste = QShortcut(QKeySequence.Paste, self)
        self._sc_paste.setContext(Qt.WidgetWithChildrenShortcut)
        self._sc_paste.activated.connect(self._on_paste)
        
        self._sc_delete = QShortcut(QKeySequence.Delete, self)
        self._sc_delete.setContext(Qt.WidgetWithChildrenShortcut)
        self._sc_delete.activated.connect(self._on_delete_clicked)

        self.input = QLineEdit()
        self.input.setPlaceholderText(placeholder)

        self.btn_edit = QPushButton(edit_label)
        self.btn_delete = QPushButton(delete_label)

        root = QVBoxLayout(self)
        root.addWidget(self.list, 1)
        root.addWidget(self.input)

        row = QHBoxLayout()
        row.addWidget(self.btn_edit)
        row.addWidget(self.btn_delete)
        root.addLayout(row)

        self.input.returnPressed.connect(self._emit_add)
        self.btn_edit.clicked.connect(self._emit_edit)
        self.list.itemDoubleClicked.connect(lambda *_: self._emit_edit())

        self.btn_delete.clicked.connect(self._on_delete_clicked)

        self.list.currentRowChanged.connect(lambda _i: self.selectionChanged.emit())
        self.list.currentItemChanged.connect(lambda _a, _b: self._update_action_enabled())

        if enable_reorder:
            self.list.setDragEnabled(True)
            self.list.setAcceptDrops(True)
            self.list.setDropIndicatorShown(True)
            self.list.setDefaultDropAction(Qt.MoveAction)
            self.list.setDragDropMode(QAbstractItemView.InternalMove)
            self.list.model().rowsMoved.connect(lambda *_: self.rowsMoved.emit())

        self._update_action_enabled()

    @staticmethod
    def make_unique_name(base: str, exists: Callable[[str], bool]) -> str:
        """
        Génère un nom unique à partir de base.
        Ex: "Omega" -> "Omega_Copy" -> "Omega_Copy2" ...
        """
        base = (base or "").strip()
        if not base:
            base = "Item"

        candidate = f"{base}_Copy"
        if not exists(candidate):
            return candidate

        i = 2
        while True:
            candidate = f"{base}_Copy{i}"
            if not exists(candidate):
                return candidate
            i += 1

    def set_clipboard_handlers(self, *, pack=None, paste=None):
        """
        pack  : callable() -> dict | None
        paste : callable(dict) -> None
        """
        self._clipboard_pack_fn = pack
        self._clipboard_paste_fn = paste

    def _on_copy(self):
        clipboard = QApplication.clipboard()

        # Mode OBJET
        if self._clipboard_pack_fn:
            payload = self._clipboard_pack_fn()
            if payload is not None:
                mime = QMimeData()
                mime.setData(
                    self.MIME,
                    json.dumps(payload).encode("utf-8")
                )
                clipboard.setMimeData(mime)
                return

        # Fallback TEXTE
        text = self.current_text()
        if text:
            clipboard.setText(text)

    def _on_paste(self):
        clipboard = QApplication.clipboard()
        mime = clipboard.mimeData()

        # Mode OBJET
        if (
            self._clipboard_paste_fn
            and mime.hasFormat(self.MIME)
        ):
            payload = json.loads(
                bytes(mime.data(self.MIME)).decode("utf-8")
            )
            self._clipboard_paste_fn(payload)
            return

        # Fallback TEXTE
        text = clipboard.text()
        if text:
            self.addRequested.emit(text.strip())

    def set_input_text(self, text: str, *, select_all: bool = True) -> None:
        self.input.setText(text)
        self.input.setFocus()
        if select_all:
            self.input.selectAll()


    def set_handlers(
        self,
        *,
        on_add: Callable[[str], None] | None = None,
        on_edit: Callable[[str], None] | None = None,
        on_delete: Callable[[], None] | None = None,
        on_selection_changed: Callable[[], None] | None = None,
        on_rows_moved: Callable[[], None] | None = None
    ) -> None:
        if on_add is not None:
            self.addRequested.connect(on_add)
        if on_edit is not None:
            self.editRequested.connect(on_edit)
        if on_delete is not None:
            self.deleteRequested.connect(on_delete)
        if on_selection_changed is not None:
            self.selectionChanged.connect(on_selection_changed)
        if on_rows_moved is not None:
            self.rowsMoved.connect(on_rows_moved)

    def set_items(self, items: list[str], *, preserve_selection: bool = True) -> None:
        """
        Remplit la liste sans effet "reset" agressif :
        - préserve la sélection si possible
        - préserve la position de scroll
        - bloque les signaux pendant TOUTE la mise à jour
        - n'émet selectionChanged que si la sélection a réellement changé
        """
        prev_text = self.current_text() if preserve_selection else None

        # Sauvegarde du scroll (sinon tu as un jump visuel)
        sb = self.list.verticalScrollBar()
        prev_scroll = sb.value()

        # On calcule la future sélection (avant d'émettre quoi que ce soit)
        target_text: str | None = None
        if prev_text and prev_text in items:
            target_text = prev_text
        elif items:
            target_text = items[0]

        # Mise à jour silencieuse
        from PySide6.QtCore import QSignalBlocker
        with QSignalBlocker(self.list):
            self.list.clear()
            self.list.addItems(items)

            if target_text:
                found = self.list.findItems(target_text, Qt.MatchExactly)
                if found:
                    self.list.setCurrentItem(found[0])
                else:
                    # Fallback sécurité
                    if self.list.count() > 0:
                        self.list.setCurrentRow(0)

        # Restaure le scroll (clamp au max)
        sb.setValue(min(prev_scroll, sb.maximum()))

        # Boutons edit/delete
        self._update_action_enabled()

        # N'émet un changement de sélection que si ça a vraiment changé
        if self.current_text() != prev_text:
            self.selectionChanged.emit()


    def current_text(self) -> str | None:
        item = self.list.currentItem()
        return item.text() if item else None

    def clear_input(self) -> None:
        self.input.clear()

    def focus_input(self, select_all: bool = False) -> None:
        self.input.setFocus()
        if select_all:
            self.input.selectAll()

    # =========================
    # Internals
    # =========================
    def _emit_add(self) -> None:
        text = self.input.text().strip()
        if not text:
            return
        self.addRequested.emit(text)
        
    def _emit_edit(self) -> None:
        """
        Ouvre une popup d'édition (texte) et émet editRequested avec la valeur validée.
        Aucun changement requis dans les autres pages : elles reçoivent toujours un str.
        """
        current = self.current_text()
        if not current:
            return

        # Valeur par défaut : l'élément sélectionné
        default_text = current

        # Fenêtre d'édition (multi-ligne si utile)
        # - Pour un usage général (ids, noms) : champ simple
        # - Pour les panels qui stockent des textes (comments etc.), on préfère multi-ligne
        #   Heuristique simple : si placeholder contient "paste multiple lines" ou "multiple lines"
        ph = (self.input.placeholderText() or "").lower()
        wants_multiline = ("multiple lines" in ph) or ("multi-lines" in ph) or ("multilines" in ph)

        if wants_multiline:
            text, ok = QInputDialog.getMultiLineText(
                self,
                "Edit",
                "Modifier :",
                default_text
            )
        else:
            text, ok = QInputDialog.getText(
                self,
                "Edit",
                "Modifier :",
                QLineEdit.Normal,
                default_text
            )

        if not ok:
            return

        new_text = (text or "").strip()
        if not new_text:
            # Validation minimale : on refuse le vide
            QMessageBox.warning(self, "Erreur", "La valeur ne peut pas être vide.")
            return

        # On émet exactement comme avant (str), donc les autres scripts ne changent pas.
        self.editRequested.emit(new_text)



    def _update_action_enabled(self) -> None:
        has_sel = self.list.currentItem() is not None
        self.btn_edit.setEnabled(has_sel)
        self.btn_delete.setEnabled(has_sel)

    def _on_delete_clicked(self) -> None:
        if not self._confirm_delete:
            self.deleteRequested.emit()
            return

        selected = self.current_text()
        msg = (
            self._confirm_delete_builder(selected)
            if self._confirm_delete_builder is not None
            else self._confirm_delete_text
        )

        res = QMessageBox.question(
            self,
            self._confirm_delete_title,
            msg,
            QMessageBox.Yes | QMessageBox.No
        )
        if res != QMessageBox.Yes:
            return

        self.deleteRequested.emit()


class NoWheelComboBox(QComboBox):
    def wheelEvent(self, event):
        # Ignore complètement la molette (ne change jamais l'item)
        event.ignore()




class ClickableImageLabel(QLabel):
    """QLabel image cliquable (double-clic) pour picker une image."""
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(180, 180)
        self.setStyleSheet("border: 1px solid #444; border-radius: 6px;")
        self.setText("Double-clic pour choisir\nune image")
        self.on_double_click = None  # callback

        # ✅ cache le pixmap original pour rescaler proprement
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
        
    @staticmethod
    def pick_image_relpath(
        parent: QWidget,
        *,
        base_dir: str,
        start_subdir: str = "",
        settings_key: str = "last_image_dir"
    ) -> str | None:
        """
        Ouvre un file dialog et retourne un chemin relatif à base_dir (slash '/').
        Retient le dernier dossier ouvert via QSettings.
        """
        settings = QSettings("Unifox", "SocialPostEditor")

        # Dossier par défaut
        default_dir = os.path.join(base_dir, start_subdir) if start_subdir else base_dir
        if not os.path.isdir(default_dir):
            default_dir = base_dir if os.path.isdir(base_dir) else os.getcwd()

        # Dernier dossier (persistant)
        last_dir = settings.value(settings_key, "", type=str)
        start_dir = last_dir if last_dir and os.path.isdir(last_dir) else default_dir

        file_path, _ = QFileDialog.getOpenFileName(
            parent,
            "Choisir une image",
            start_dir,
            "Images (*.png *.jpg *.jpeg *.webp);;Tous (*.*)"
        )
        if not file_path:
            return None

        # Mémorise le dossier choisi
        settings.setValue(settings_key, os.path.dirname(file_path))

        # Relatif à base_dir
        try:
            rel = os.path.relpath(file_path, base_dir)
        except ValueError:
            rel = os.path.basename(file_path)

        return rel.replace("\\", "/")

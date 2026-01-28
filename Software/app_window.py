from __future__ import annotations
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QTabWidget,
    QFileDialog, QMessageBox, QApplication
)
from qt_material import apply_stylesheet
import traceback

from state import AppState
from theme_manager import ThemeManager
from io_json import load_json, save_json
from io_js_export import export_to_js

from pages.page_public_profile import PagePublicProfile
from pages.page_heroine_profile import PageHeroineProfile
from pages.page_comments import PageComments
from pages.page_usernames import PageUsernames
from pages.page_emoji import PageEmoji
from pages.page_validate import PageValidate


class AppWindow(QMainWindow):
    def __init__(self, app: QApplication, theme: ThemeManager):
        super().__init__()
        self._base_title = "NAS Social Post Helper"
        self.setWindowTitle(self._base_title)

        self.resize(1200, 720)
        self.setMinimumSize(600, 400)


        self._app = app
        self._theme = theme
        self.state = AppState()
        self.state.dirtyChanged.connect(self._update_window_title)

        self._build_ui()
        self._build_menu()
        self._try_autoload_database_json()

    # -------------------------
    # UI
    # -------------------------
    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)

        layout = QVBoxLayout(root)

        # Onglets en haut
        self.tabs = QTabWidget()
        self.tabs.setMovable(False)         # True si tu veux pouvoir les réordonner
        self.tabs.setTabsClosable(False)    # True si tu veux une croix (pas utile ici)
        self.tabs.setDocumentMode(True)     # Style plus "moderne" sur certains thèmes

        # Pages (on garde des références pour la navigation)
        self.page_public = PagePublicProfile(self.state)
        self.page_heroine = PageHeroineProfile(self.state)
        self.page_comments = PageComments(self.state)
        self.page_usernames = PageUsernames(self.state)
        self.page_emoji = PageEmoji(self.state)
        self.page_validate = PageValidate(self.state)

        self.tabs.addTab(self.page_public, "Post Profil Public")
        self.tabs.addTab(self.page_heroine, "Post Profil Héroïne")
        self.tabs.addTab(self.page_comments, "Commentaire")
        self.tabs.addTab(self.page_usernames, "Username")
        self.tabs.addTab(self.page_emoji, "Emoji")
        self.tabs.addTab(self.page_validate, "Validation")

        self.page_validate.navigateRequested.connect(self._navigate_from_validation)


        layout.addWidget(self.tabs)

    def _navigate_from_validation(self, path: str) -> None:
        parts = path.split(".")
        if not parts:
            return

        # --- emoji preset manquant sur un post
        # profiles.<pid>.posts.<postKey>.emojiPreset
        if len(parts) >= 5 and parts[0] == "profiles" and parts[2] == "posts":
            profile_id = parts[1]
            post_key = parts[3]
            field = parts[4] if len(parts) > 4 else ""
            self.tabs.setCurrentWidget(self.page_public)
            if hasattr(self.page_public, "goto_post"):
                self.page_public.goto_post(profile_id, post_key, field)
            return

        # heroine.posts.<postKey>.emojiPreset / commentsSet
        if len(parts) >= 4 and parts[0] == "heroine" and parts[1] == "posts":
            post_key = parts[2]
            field = parts[3] if len(parts) > 3 else ""
            self.tabs.setCurrentWidget(self.page_heroine)
            if hasattr(self.page_heroine, "goto_post"):
                self.page_heroine.goto_post(post_key, field)
            return

        # commentBlocks.<blockId>.usernamePool
        if len(parts) >= 2 and parts[0] == "commentBlocks":
            block_id = parts[1]
            self.tabs.setCurrentWidget(self.page_comments)
            if hasattr(self.page_comments, "goto_block"):
                self.page_comments.goto_block(block_id)
            return

        # commentSets.<setId>[i]
        if len(parts) >= 2 and parts[0] == "commentSets":
            set_id = parts[1]
            self.tabs.setCurrentWidget(self.page_comments)
            if hasattr(self.page_comments, "goto_set"):
                self.page_comments.goto_set(set_id)
            return

        # usernames.<poolId>
        if len(parts) >= 2 and parts[0] == "usernames":
            pool_id = parts[1]
            self.tabs.setCurrentWidget(self.page_usernames)
            if hasattr(self.page_usernames, "goto_pool"):
                self.page_usernames.goto_pool(pool_id)
            return

        # emojiPresets.<presetId>
        if len(parts) >= 2 and parts[0] == "emojiPresets":
            preset_id = parts[1]
            self.tabs.setCurrentWidget(self.page_emoji)
            if hasattr(self.page_emoji, "goto_preset"):
                self.page_emoji.goto_preset(preset_id) 
            return

    # -------------------------
    # Menus
    # -------------------------
    def _build_menu(self) -> None:
        mb = self.menuBar()

        # Fichier
        menu_file = mb.addMenu("Fichier")

        act_load = menu_file.addAction("Charger (JSON)")
        act_save = menu_file.addAction("Enregistrer (JSON)")
        menu_file.addSeparator()
        act_export = menu_file.addAction("Export (JS)")

        act_load.triggered.connect(self.action_load_json)
        act_save.triggered.connect(self.action_save_json)
        act_export.triggered.connect(self.action_export_js)

        # Options
        menu_opt = mb.addMenu("Options")

        # Dark/Light
        act_dark = menu_opt.addAction("Mode sombre")
        act_dark.setCheckable(True)
        act_dark.setChecked(self._theme.is_dark)

        def on_dark_toggled(checked: bool) -> None:
            self._theme.set_dark(checked)
            self._apply_theme()

        act_dark.toggled.connect(on_dark_toggled)

        menu_opt.addSeparator()

        # Thèmes (couleurs) : on expose juste un choix par index
        submenu_theme = menu_opt.addMenu("Couleur (Qt-Material)")

        themes = self._theme.themes_dark if self._theme.is_dark else self._theme.themes_light
        # On construit dynamiquement, et on reconstruira quand on switch dark/light (simple V0)
        for i, name in enumerate(themes):
            a = submenu_theme.addAction(name)
            a.setCheckable(True)
            a.setChecked(i == self._theme.theme_index)

            def make_handler(idx: int):
                def handler():
                    self._theme.set_theme_index(idx)
                    self._apply_theme()
                    # Update checks
                    for j, act in enumerate(submenu_theme.actions()):
                        act.setChecked(j == idx)
                return handler

            a.triggered.connect(make_handler(i))

    def _apply_theme(self) -> None:
        """
        Réapplique le thème à l'application.
        """
        apply_stylesheet(self._app, theme=self._theme.current_theme_file())

    def _try_autoload_database_json(self) -> None:
        """
        Charge automatiquement Database.json si présent à la racine du projet (à côté de Start.pyw).
        """
        try:
            root = Path(__file__).resolve().parent.parent  # si app_window.py est dans Software/
            # Si app_window.py est directement dans Software/, root = dossier parent de Software
            candidate = root / "Database.json"
            if not candidate.exists():
                return

            obj = load_json(str(candidate))
            self.state.set_data(obj, path=str(candidate))
        except Exception as e:
            # On ne spam pas, on affiche juste si tu veux
            # QMessageBox.warning(self, "Auto-load Database.json échoué", str(e))
            pass

    def closeEvent(self, event) -> None:
        # Si rien n'a changé, on ferme direct
        if not self.state.is_dirty:
            event.accept()
            return

        box = QMessageBox(self)
        box.setWindowTitle("Modifications non enregistrées")
        box.setText("Tu veux enregistrer les modifications avant de quitter ?")
        box.setIcon(QMessageBox.Question)

        btn_save = box.addButton("Enregistrer", QMessageBox.AcceptRole)
        btn_no = box.addButton("Ne pas enregistrer", QMessageBox.DestructiveRole)
        btn_cancel = box.addButton("Annuler", QMessageBox.RejectRole)

        box.setDefaultButton(btn_save)
        box.exec()

        clicked = box.clickedButton()

        if clicked == btn_cancel:
            event.ignore()
            return

        if clicked == btn_no:
            event.accept()
            return

        # Enregistrer
        path = self.state.current_path
        if not path:
            path, _ = QFileDialog.getSaveFileName(self, "Enregistrer JSON", "Database.json", "JSON (*.json)")
            if not path:
                event.ignore()
                return
            self.state.current_path = path

        try:
            save_json(path, self.state.data)
            self.state.set_dirty(False)
            event.accept()
        except Exception as e:
            QMessageBox.critical(self, "Erreur sauvegarde", str(e))
            event.ignore()


    # -------------------------
    # Actions Fichier
    # -------------------------
    def action_load_json(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Charger JSON", "", "JSON (*.json)")
        if not path:
            return
        try:
            obj = load_json(path)
            self.state.set_data(obj, path=path)
            QMessageBox.information(self, "OK", "JSON chargé.")
        except Exception as e:
            QMessageBox.critical(self, "Erreur", str(e))


    def action_save_json(self) -> None:
        path = self.state.current_path
        if not path:
            path, _ = QFileDialog.getSaveFileName(self, "Enregistrer JSON", "social_posts.json", "JSON (*.json)")
            if not path:
                return
            self.state.current_path = path

        try:
            save_json(path, self.state.data)
            QMessageBox.information(self, "OK", "JSON enregistré.")
            self.state.set_dirty(False)
        except Exception as e:
            QMessageBox.critical(self, "Erreur", str(e))

    def action_export_js(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Exporter JS", "NAS_SocialData_MZ.js", "JavaScript (*.js)")
        if not path:
            return
        try:
            js = export_to_js(self.state.data)
            with open(path, "w", encoding="utf-8") as f:
                f.write(js)
            QMessageBox.information(self, "OK", "JS exporté.")
        except Exception:
            tb = traceback.format_exc()
            print(tb)  # console
            QMessageBox.critical(self, "Export JS - erreur", tb)

    def _update_window_title(self, is_dirty: bool) -> None:
        name = "Sans nom"
        if self.state.current_path:
            name = Path(self.state.current_path).name

        star = " *" if is_dirty else ""
        self.setWindowTitle(f"{self._base_title} — {name}{star}")


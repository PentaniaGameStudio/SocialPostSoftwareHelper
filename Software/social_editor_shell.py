# Software/ui_helpers/social_editor_shell.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel,
    QStackedWidget, QPushButton
)

from ui_helpers import ListPanel


HELP_CONDITION_JS = r"""
<b>conditionJS — Lecture (doit retourner true/false)</b><br><br>

<b>Contexte (<code>ctx</code>)</b><br>
<ul>
  <li><b>Infos post</b> : <code>ctx.timeSlot</code>, <code>ctx.profileId</code>, <code>ctx.pictureName</code>, <code>ctx.postKey</code></li>
  <li><b>Interne social</b> : <code>ctx.flags</code>, <code>ctx.counters</code>, <code>ctx.state</code></li>
  <li><b>RPG Maker MZ</b> : <code>ctx.$gameSwitches</code>, <code>ctx.$gameVariables</code>, <code>ctx.$gameParty</code>, <code>ctx.$gameActors</code></li>
</ul>

<b>Switches (lecture)</b><br>
<pre style="white-space:pre-wrap;">
ctx.$gameSwitches.value(12)                 // true/false
!ctx.$gameSwitches.value(12)                // négation
</pre>

<b>Variables (lecture)</b><br>
<pre style="white-space:pre-wrap;">
ctx.$gameVariables.value(34)                // nombre/texte
ctx.$gameVariables.value(34) >= 10
</pre>

<b>Flags internes (lecture)</b><br>
<pre style="white-space:pre-wrap;">
ctx.flags["hasMetGrey"] === true
ctx.flags["route"] === "CatElf"
</pre>

<b>Counters internes (lecture)</b><br>
<pre style="white-space:pre-wrap;">
(ctx.counters["lux"] ?? 0) >= 3
</pre>

<b>Exemples complets</b>
<pre style="white-space:pre-wrap;">
   <i>Visible seulement la nuit + switch 12 ON</i>
return ctx.timeSlot === "night" && ctx.$gameSwitches.value(12);

   <i>Variable 34 au moins 10</i>
return ctx.$gameVariables.value(34) >= 10;

   <i>Flag interne (fallback false)</i>
return (ctx.flags["unlocked"] ?? false) === true;
</pre>
"""

HELP_EFFECT_JS = r"""
<b>effectJs — Écriture (side-effects, pas de return requis)</b><br><br>

<b>Switches (écriture)</b><br>
<pre style="white-space:pre-wrap;">
ctx.$gameSwitches.setValue(12, true)
ctx.$gameSwitches.setValue(12, false)
</pre>

<b>Variables (écriture)</b><br>
<pre style="white-space:pre-wrap;">
ctx.$gameVariables.setValue(34, 9)
ctx.$gameVariables.setValue(34, ctx.$gameVariables.value(34) + 1)  // +1
</pre>

<b>Flags internes (écriture)</b><br>
<pre style="white-space:pre-wrap;">
ctx.flags["hasMetGrey"] = true
ctx.flags["route"] = "CatElf"
</pre>

<b>Counters internes (écriture)</b><br>
<pre style="white-space:pre-wrap;">
ctx.counters["lux"] = (ctx.counters["lux"] ?? 0) + 1
ctx.counters["seenPosts"] = (ctx.counters["seenPosts"] ?? 0) + 1
</pre>

<b>Accès aux infos du post (lecture utile pour écrire)</b><br>
<pre style="white-space:pre-wrap;">
// Exemple: flag par post
ctx.flags["seen_" + ctx.postKey] = true

// Exemple: compteur par timeSlot
ctx.counters["seen_" + ctx.timeSlot] = (ctx.counters["seen_" + ctx.timeSlot] ?? 0) + 1
</pre>

<b>Exemples complets</b>
<pre style="white-space:pre-wrap;">
   <i>Active un switch et incrémente une variable</i>
ctx.$gameSwitches.setValue(12, true);
ctx.$gameVariables.setValue(34, ctx.$gameVariables.value(34) + 1);

   <i>Marque le post comme vu</i>
ctx.flags["seen_" + ctx.postKey] = true;
</pre>
"""

TIME_SLOTS = ("morning 🌤️", "day 🏙️", "sunset 🌇", "night 🌃", "all ⚡")

@dataclass(frozen=True)
class ShellTexts:
    profiles_title: str = "Profiles"
    posts_title: str = "Posts"
    profiles_placeholder: str = "Add profile… (Enter)"
    posts_placeholder: str = "Add post… (Enter)"
    btn_profile: str = "Profile"
    btn_post: str = "Post"


class SocialEditorShell(QWidget):
    """
    Shell réutilisable:
      - 2 rubans à gauche (profiles + posts)
      - boutons en haut à droite pour switch (Profile/Post)
      - éditeur à droite en QStackedWidget
    """
    profileSelected = Signal(object)          # profile_id | None
    postSelected = Signal(object, object)     # profile_id | None, post_id | None

    # Profil implicite quand le ruban profiles est caché
    HIDDEN_PROFILE_ID = "__HIDDEN_PROFILE__"

    def __init__(
        self,
        *,
        profile_editor: QWidget,
        post_editor: QWidget,
        texts: ShellTexts = ShellTexts(),
        enable_profiles_crud: bool = True,
        enable_posts_crud: bool = True,
        show_profiles_panel: bool = True,   # ✅ NEW
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._texts = texts
        self._show_profiles_panel = show_profiles_panel

        # callbacks
        self._list_profiles: Callable[[], list[str]] | None = None
        self._list_posts: Callable[[str], list[str]] | None = None

        self._on_add_profile: Callable[[str], None] | None = None
        self._on_rename_profile: Callable[[str], None] | None = None
        self._on_delete_profile: Callable[[], None] | None = None

        self._on_add_post: Callable[[str], None] | None = None
        self._on_rename_post: Callable[[str], None] | None = None
        self._on_delete_post: Callable[[], None] | None = None

        self._on_profile_selected: Callable[[str | None], None] | None = None
        self._on_post_selected: Callable[[str | None, str | None], None] | None = None

        self._building_ui = False

        # ======================
        # UI
        # ======================
        root = QHBoxLayout(self)

        # ----- Left ribbons (✅ 2 colonnes côte à côte)
        left = QHBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(12)

        # Colonne PROFILES
        profiles_col_w = QWidget()
        profiles_col = QVBoxLayout(profiles_col_w)
        profiles_col.setContentsMargins(0, 0, 0, 0)
        profiles_col.setSpacing(6)

        self.lbl_profiles_title = QLabel(self._texts.profiles_title)
        profiles_col.addWidget(self.lbl_profiles_title)

        self.panel_profiles = ListPanel(
            placeholder=self._texts.profiles_placeholder,
            edit_label="Rename",
            delete_label="Delete",
            confirm_delete=True,
            confirm_delete_title="Supprimer",
            confirm_delete_builder=lambda sel: f"Supprimer le profil '{sel}' ?",
        )
        profiles_col.addWidget(self.panel_profiles, 1)

        # Colonne POSTS
        posts_col_w = QWidget()
        posts_col = QVBoxLayout(posts_col_w)
        posts_col.setContentsMargins(0, 0, 0, 0)
        posts_col.setSpacing(6)

        self.lbl_posts_title = QLabel(self._texts.posts_title)
        posts_col.addWidget(self.lbl_posts_title)

        self.panel_posts = ListPanel(
            placeholder=self._texts.posts_placeholder,
            edit_label="Rename",
            delete_label="Delete",
            confirm_delete=True,
            confirm_delete_title="Supprimer",
            confirm_delete_builder=lambda sel: f"Supprimer le post '{sel}' ?",
        )
        posts_col.addWidget(self.panel_posts, 1)

        # Ajout côte à côte (stretch = partage largeur)
        left.addWidget(profiles_col_w, 1)
        left.addWidget(posts_col_w, 1)

        # ✅ Cache totalement la colonne "Profiles" si demandé
        if not self._show_profiles_panel:
            profiles_col_w.hide()
            # optionnel: enlève l'espace visuel entre colonnes si tu veux
            left.setSpacing(0)

        # ----- Right: top buttons + stacked
        right = QVBoxLayout()

        topbar = QHBoxLayout()
        self.btn_show_profile = QPushButton(self._texts.btn_profile)
        self.btn_show_post = QPushButton(self._texts.btn_post)

        self.btn_show_profile.setMinimumWidth(120)
        self.btn_show_post.setMinimumWidth(120)

        self.btn_show_profile.clicked.connect(self.show_profile_editor)
        self.btn_show_post.clicked.connect(self.show_post_editor)

        topbar.addStretch(1)
        topbar.addWidget(self.btn_show_profile)
        topbar.addWidget(self.btn_show_post)
        topbar.addStretch(1)

        right.addLayout(topbar)

        self.stack = QStackedWidget()
        self.stack.addWidget(profile_editor)  # index 0
        self.stack.addWidget(post_editor)     # index 1
        self.stack.setCurrentIndex(0)

        right.addWidget(self.stack, 1, alignment=Qt.AlignHCenter | Qt.AlignTop)

        root.addLayout(left, 1)
        root.addLayout(right, 3)


        # ======================
        # Wiring selection
        # ======================
        self.panel_profiles.selectionChanged.connect(self._handle_profile_clicked)
        self.panel_posts.selectionChanged.connect(self._handle_post_clicked)
        self.panel_profiles.list.itemClicked.connect(lambda *_: self._handle_profile_clicked())
        self.panel_posts.list.itemClicked.connect(lambda *_: self._handle_post_clicked())

        # ======================
        # CRUD
        # ======================
        # Profiles CRUD uniquement si ruban visible
        if enable_profiles_crud and self._show_profiles_panel:
            self.panel_profiles.addRequested.connect(lambda t: self._on_add_profile(t) if self._on_add_profile else None)
            self.panel_profiles.editRequested.connect(lambda t: self._on_rename_profile(t) if self._on_rename_profile else None)
            self.panel_profiles.deleteRequested.connect(lambda: self._on_delete_profile() if self._on_delete_profile else None)
        else:
            self._disable_panel_crud(self.panel_profiles)

        if enable_posts_crud:
            self.panel_posts.addRequested.connect(lambda t: self._on_add_post(t) if self._on_add_post else None)
            self.panel_posts.editRequested.connect(lambda t: self._on_rename_post(t) if self._on_rename_post else None)
            self.panel_posts.deleteRequested.connect(lambda: self._on_delete_post() if self._on_delete_post else None)
        else:
            self._disable_panel_crud(self.panel_posts)

        self._sync_mode_buttons()

    # =========================================================
    # Public API
    # =========================================================
    def set_bindings(
        self,
        *,
        list_profiles: Callable[[], list[str]] | None = None,
        list_posts: Callable[[str], list[str]] | None = None,
        on_profile_selected: Callable[[str | None], None] | None = None,
        on_post_selected: Callable[[str | None, str | None], None] | None = None,
        on_add_profile: Callable[[str], None] | None = None,
        on_rename_profile: Callable[[str], None] | None = None,
        on_delete_profile: Callable[[], None] | None = None,
        on_add_post: Callable[[str], None] | None = None,
        on_rename_post: Callable[[str], None] | None = None,
        on_delete_post: Callable[[], None] | None = None,
    ) -> None:
        self._list_profiles = list_profiles
        self._list_posts = list_posts

        self._on_profile_selected = on_profile_selected
        self._on_post_selected = on_post_selected

        self._on_add_profile = on_add_profile
        self._on_rename_profile = on_rename_profile
        self._on_delete_profile = on_delete_profile

        self._on_add_post = on_add_post
        self._on_rename_post = on_rename_post
        self._on_delete_post = on_delete_post

    def reload_lists(self, *, preserve_selection: bool = True) -> None:
        """
        Recharge profiles/posts.
        Si le ruban Profiles est caché, on utilise un profil implicite (HIDDEN_PROFILE_ID).
        """
        if not self._list_posts:
            return

        # Si ruban visible, il faut list_profiles
        if self._show_profiles_panel and not self._list_profiles:
            return

        self._building_ui = True
        try:
            # Profiles (si visibles)
            if self._show_profiles_panel:
                profiles = self._list_profiles() if self._list_profiles else []
                self.panel_profiles.set_items(profiles, preserve_selection=preserve_selection)
                prof = self.current_profile_id()
            else:
                # ✅ profil implicite
                prof = self.HIDDEN_PROFILE_ID

            # Aucun profil => pas de posts
            if not prof:
                self.panel_posts.set_items([], preserve_selection=False)
                self.show_profile_editor()
                self._sync_mode_buttons()
                return

            posts = self._list_posts(prof)
            self.panel_posts.set_items(posts, preserve_selection=preserve_selection)

            # Si aucun post sélectionné -> mode profil par défaut
            if not self.current_post_id():
                self.show_profile_editor()

            self._sync_mode_buttons()
        finally:
            self._building_ui = False

    def current_profile_id(self) -> str | None:
        if not self._show_profiles_panel:
            return self.HIDDEN_PROFILE_ID
        return self.panel_profiles.current_text()

    def current_post_id(self) -> str | None:
        return self.panel_posts.current_text()

    def show_profile_editor(self) -> None:
        self.stack.setCurrentIndex(0)
        self._sync_mode_buttons()

    def show_post_editor(self) -> None:
        # pas de post sélectionné => ne switch pas
        if not self.current_post_id():
            self.stack.setCurrentIndex(0)
        else:
            self.stack.setCurrentIndex(1)
        self._sync_mode_buttons()

    def clear_post_selection(self) -> None:
        self.panel_posts.list.blockSignals(True)
        try:
            self.panel_posts.list.setCurrentRow(-1)
        finally:
            self.panel_posts.list.blockSignals(False)

    def set_profiles_locked(self, locked: bool) -> None:
        self.panel_profiles.input.setEnabled(not locked)
        self.panel_profiles.btn_edit.setEnabled(not locked and self.panel_profiles.current_text() is not None)
        self.panel_profiles.btn_delete.setEnabled(not locked and self.panel_profiles.current_text() is not None)

    # =========================================================
    # Internals
    # =========================================================
    @staticmethod
    def _disable_panel_crud(panel: ListPanel) -> None:
        # Note: ListPanel peut avoir btn_add suivant ton implémentation.
        # On coupe au minimum input/edit/delete (comme ton code d'origine).
        panel.input.setEnabled(False)
        panel.btn_edit.setEnabled(False)
        panel.btn_delete.setEnabled(False)
        if hasattr(panel, "btn_add"):
            panel.btn_add.setEnabled(False)

    def _sync_mode_buttons(self) -> None:
        has_post = bool(self.current_post_id())

        # Si pas de post, on empêche d'aller sur l'éditeur post
        self.btn_show_post.setEnabled(has_post)

        # feedback léger: désactive le bouton de la page courante
        idx = self.stack.currentIndex()
        self.btn_show_profile.setEnabled(idx != 0)
        self.btn_show_post.setEnabled(has_post and idx != 1)

    def _handle_profile_clicked(self) -> None:
        # Si le ruban profiles est caché, on ignore (sécurité)
        if not self._show_profiles_panel:
            return

        if self._building_ui:
            return

        prof = self.current_profile_id()
        self.profileSelected.emit(prof)

        # Rebuild posts list for this profile
        if self._list_posts and prof:
            self._building_ui = True
            try:
                posts = self._list_posts(prof)
                self.panel_posts.set_items(posts, preserve_selection=False)
                self.clear_post_selection()
            finally:
                self._building_ui = False
        else:
            self.panel_posts.set_items([], preserve_selection=False)
            self.clear_post_selection()

        # Switch editor to profile view
        self.show_profile_editor()

        if self._on_profile_selected:
            self._on_profile_selected(prof)

        # Inform post selection cleared
        self.postSelected.emit(prof, None)
        if self._on_post_selected:
            self._on_post_selected(prof, None)

        self._sync_mode_buttons()

    def _handle_post_clicked(self) -> None:
        if self._building_ui:
            return

        prof = self.current_profile_id()
        post = self.current_post_id()

        if not post:
            self.show_profile_editor()
            self.postSelected.emit(prof, None)
            if self._on_post_selected:
                self._on_post_selected(prof, None)
            self._sync_mode_buttons()
            return

        self.show_post_editor()
        self.postSelected.emit(prof, post)
        if self._on_post_selected:
            self._on_post_selected(prof, post)

        self._sync_mode_buttons()

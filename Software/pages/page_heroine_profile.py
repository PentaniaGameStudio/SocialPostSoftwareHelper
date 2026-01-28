# Software/pages/page_heroine_profile.py
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, QSignalBlocker
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QMessageBox, QInputDialog, QAbstractItemView
)

from state import AppState
from social_editor_shell import SocialEditorShell, ShellTexts
from ui_helpers import ListPanel
from pages.social_profile_base import SocialProfilePageBase
import copy


class PageHeroineProfile(SocialProfilePageBase):
    """
    Page Héroïne (profil unique) utilisant SocialEditorShell:
      - Clic profil -> éditeur profil
      - Clic post   -> éditeur post

    Data (state.data):
      state.data["heroine"] = {
        "defaultDisplayName": str,
        "defaultProfileImage": str,
        "posts": { postId: { ... } }
      }

    Dépendances:
      state.data["emojiPresets"] : dict
      state.data["commentSets"]  : dict
    """

    PROFILE_ID = "Heroine"
    PROFILE_GROUP_TITLE = "Heroine Profile"

    def __init__(self, state: AppState):
        super().__init__(state)

        # Shell
        self.shell = SocialEditorShell(
            profile_editor=self._profile_editor,
            post_editor=self._post_editor,
            texts=ShellTexts(
                profiles_title="Profile",
                posts_title="Posts",
                profiles_placeholder="(profil unique)",
                posts_placeholder="Add post id (Enter) e.g. Morning_Cookie",
            ),
            enable_profiles_crud=False,
            enable_posts_crud=True,
            show_profiles_panel=False,  # ✅ cache totalement le ruban Profiles
        )

        layout = QVBoxLayout(self)
        layout.addWidget(self.shell, 1)

        # Bind shell callbacks
        self.shell.set_bindings(
            list_profiles=self._list_profiles,
            list_posts=self._list_posts,
            on_profile_selected=self._on_profile_selected,
            on_post_selected=self._on_post_selected,
            on_add_post=self._post_add,
            on_rename_post=self._post_rename_from_typed,
            on_delete_post=self._post_delete,
        )
        
        self.shell.panel_posts.set_clipboard_handlers(
            pack=self._pack_post,
            paste=self._paste_post,
        )

        # --- Drag & drop interne pour réordonner les posts
        self.shell.panel_posts.list.setDragEnabled(True)
        self.shell.panel_posts.list.setAcceptDrops(True)
        self.shell.panel_posts.list.setDropIndicatorShown(True)
        self.shell.panel_posts.list.setDefaultDropAction(Qt.MoveAction)
        self.shell.panel_posts.list.setDragDropMode(QAbstractItemView.InternalMove)
        self.shell.panel_posts.list.model().rowsMoved.connect(self._on_posts_reordered)

        # Empêche saisie profile panel
        self.shell.panel_profiles.input.setEnabled(False)
        self.shell.panel_profiles.btn_edit.setEnabled(False)
        self.shell.panel_profiles.btn_delete.setEnabled(False)

        # State wiring
        self.state.dataChanged.connect(self.reload_from_state)

        # Init
        self.reload_from_state()

    def _current_profile_id(self) -> str | None:
        return self.PROFILE_ID

    def _current_post_id(self) -> str | None:
        return self.shell.current_post_id()

    def _get_profile_data(self, _profile_id: str) -> dict[str, Any]:
        return self._ensure_heroine_root()

    def _get_post_data(self, _profile_id: str | None, post_id: str) -> dict[str, Any]:
        return self._get_post(post_id)

    def _post_image_subdir(self, _profile_id: str | None) -> str:
        return "Picture/Naelith"

    def _pack_post(self) -> object | None:
        post_id = self.shell.current_post_id()
        if not post_id:
            return None

        posts = self._heroine_posts()
        if post_id not in posts:
            return None

        return {
            "kind": "heroine_post",
            "id": post_id,
            "data": copy.deepcopy(posts[post_id]),
        }


    def _paste_post(self, payload: object) -> bool:
        if not isinstance(payload, dict) or payload.get("kind") != "heroine_post":
            return False

        posts = self._heroine_posts()

        base_id = str(payload.get("id") or "Post").strip() or "Post"
        data = payload.get("data")
        if not isinstance(data, dict):
            return False

        new_id = ListPanel.make_unique_name(base_id, exists=lambda s: s in posts)  # <= il faut importer ListPanel
        new_data = copy.deepcopy(data)
        new_data["order"] = self.shell.panel_posts.list.count()
        posts[new_id] = new_data

        self.state.mark_dirty()

        with self._ui_guard():
            self.shell.reload_lists(preserve_selection=False)
            found = self.shell.panel_posts.list.findItems(new_id, Qt.MatchExactly)
            if found:
                self.shell.panel_posts.list.setCurrentItem(found[0])
                self.shell.panel_posts.list.scrollToItem(found[0])

        return True

    def _ensure_heroine_root(self) -> dict[str, Any]:
        root = self.state.data.setdefault("heroine", {})
        root.setdefault("defaultDisplayName", "")
        root.setdefault("defaultProfileImage", "")
        root.setdefault("posts", {})
        return root

    def _heroine_posts(self) -> dict[str, Any]:
        return self._ensure_heroine_root().setdefault("posts", {})

    def _get_post(self, post_id: str) -> dict[str, Any]:
        posts = self._heroine_posts()
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

    @staticmethod
    def _to_int(text: str, default: int = 0) -> int:
        try:
            return int(text)
        except (TypeError, ValueError):
            return default

    def _list_profiles(self) -> list[str]:
        # profil unique => toujours affiché
        self._ensure_heroine_root()
        return [self.PROFILE_ID]

    def _list_posts(self, _profile_id: str) -> list[str]:
        self._ensure_post_orders()
        return [
            post_id for post_id, _ in sorted(
                self._heroine_posts().items(),
                key=lambda kv: self._to_int(kv[1].get("order", 0), 0),
            )
        ]

    def _ensure_post_orders(self) -> None:
        posts = self._heroine_posts()
        missing = [pid for pid, p in posts.items() if "order" not in p]
        if not missing:
            return

        for i, pid in enumerate(sorted(posts.keys())):
            posts.setdefault(pid, {})["order"] = i

    def _rebuild_post_orders(self) -> None:
        posts = self._heroine_posts()
        for i in range(self.shell.panel_posts.list.count()):
            item = self.shell.panel_posts.list.item(i)
            if not item:
                continue
            post_id = item.text()
            if post_id in posts:
                posts[post_id]["order"] = i

    def _on_posts_reordered(self, *_args) -> None:
        if self._building_ui:
            return
        self._rebuild_post_orders()
        self.state.mark_dirty()

    def _on_profile_selected(self, _profile_id: str | None) -> None:
        # Quand on clique le profil => refresh profil
        self._refresh_profile_editor()

    def _on_post_selected(self, _profile_id: str | None, post_id: str | None) -> None:
        # Quand on clique un post => refresh post editor (ou disable)
        self._refresh_post_editor(post_id)

    # =========================================================
    # Build editors
    # =========================================================
    def goto_post(self, profile_id: str, post_key: str, field: str = "") -> None:
        with self._ui_guard():
            self._refresh_profiles(preserve_selection=False)
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


    def reload_from_state(self) -> None:
        with self._ui_guard():
            self._ensure_heroine_root()

            # Reload lists via shell
            self.shell.reload_lists(preserve_selection=True)

            # Always refresh dropdowns (presets/sets)
            self._refresh_emoji_preset_dropdown()
            self._refresh_comment_set_dropdown()

            # Refresh current editor page
            self._refresh_profile_editor()

            post_id = self.shell.current_post_id()
            self._refresh_post_editor(post_id)

    def _refresh_profile_editor(self) -> None:
        root = self._ensure_heroine_root()
        with self._ui_guard():
            self.le_display_name.setText(root.get("defaultDisplayName", "") or "")
            self._set_image_preview(self.lbl_profile_img, root.get("defaultProfileImage", "") or "")

    def _refresh_post_editor(self, post_id: str | None) -> None:
        enabled = bool(post_id)
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

        post = self._get_post(post_id)

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

    def _post_add(self, post_id: str) -> None:
        post_id = post_id.strip()
        if not post_id:
            return

        posts = self._heroine_posts()
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
            "lewdCondition": {"min": 0, "max": 999999},
            "order": self.shell.panel_posts.list.count(),
        }

        self.state.mark_dirty()
        self.shell.panel_posts.clear_input()

        with self._ui_guard():
            self.shell.reload_lists(preserve_selection=False)
            found = self.shell.panel_posts.list.findItems(post_id, Qt.MatchExactly)
            if found:
                self.shell.panel_posts.list.setCurrentItem(found[0])
            # Shell va afficher l'éditeur post via sélectionChanged

    def _post_rename_from_typed(self, typed: str) -> None:
        old = self.shell.current_post_id()
        if not old:
            return

        # UX: si champ vide -> pré-remplir + focus
        if not typed.strip():
            self.shell.panel_posts.input.setText(old)
            self.shell.panel_posts.focus_input(select_all=True)
            return

        self._post_rename(old, typed.strip())

    def _post_rename(self, old: str, new: str) -> None:
        posts = self._heroine_posts()
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
            self.shell.reload_lists(preserve_selection=False)
            found = self.shell.panel_posts.list.findItems(new, Qt.MatchExactly)
            if found:
                self.shell.panel_posts.list.setCurrentItem(found[0])

    def _post_delete(self) -> None:
        post_id = self.shell.current_post_id()
        if not post_id:
            return

        # ListPanel fait déjà la confirmation (confirm_delete=True)
        self._heroine_posts().pop(post_id, None)
        self.state.mark_dirty()

        with self._ui_guard():
            self.shell.reload_lists(preserve_selection=False)
            # Si plus de sélection -> on revient sur profil
            if not self.shell.current_post_id():
                self.shell.show_profile_editor()
            self._refresh_post_editor(self.shell.current_post_id())

    # =========================================================
    # Post field changes
    # =========================================================
    def _select_comment_set(self, set_id: str) -> None:
        with QSignalBlocker(self.cb_comment_set):
            idx = self.cb_comment_set.findText(set_id)
            self.cb_comment_set.setCurrentIndex(idx if idx >= 0 else 0)

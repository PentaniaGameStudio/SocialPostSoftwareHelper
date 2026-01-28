# Software/pages/page_public_profile.py
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, QSignalBlocker
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QMessageBox, QAbstractItemView
)

from state import AppState
from social_editor_shell import SocialEditorShell, ShellTexts
from ui_helpers import ListPanel
from pages.social_profile_base import SocialProfilePageBase
import copy

PUBLIC_PROFILES_KEY = "profiles"

class PagePublicProfile(SocialProfilePageBase):
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

    PROFILE_GROUP_TITLE = "Public Profile"
    USES_PROFILE_SCOPE_FOR_POST = True

    def __init__(self, state: AppState):
        super().__init__(state)

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

    def _current_profile_id(self) -> str | None:
        return self.shell.current_profile_id()

    def _current_post_id(self) -> str | None:
        return self.shell.current_post_id()

    def _get_profile_data(self, profile_id: str) -> dict[str, Any]:
        return self._get_profile(profile_id)

    def _get_post_data(self, profile_id: str | None, post_id: str) -> dict[str, Any]:
        if not profile_id:
            return {}
        return self._get_post(profile_id, post_id)

    def _post_image_subdir(self, profile_id: str | None) -> str:
        return f"Picture/{profile_id}" if profile_id else "Picture"


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
    def _select_comment_set(self, set_id: str) -> None:
        with QSignalBlocker(self.cb_comment_set):
            idx = self.cb_comment_set.findText(set_id)
            self.cb_comment_set.setCurrentIndex(idx if idx >= 0 else 0)

# Software/state.py

from __future__ import annotations

from typing import Any, Dict
from PySide6.QtCore import QObject, Signal


def default_data() -> Dict[str, Any]:
    return {
        "profiles": {},
        "heroine": {"posts": {}},
        "usernames": {},
        "commentBlocks": {},
        "commentSets": {},
        "emojiPresets": {}
    }


class AppState(QObject):
    dataChanged = Signal()
    dirtyChanged = Signal(bool)

    def __init__(self) -> None:
        super().__init__()
        self.data: Dict[str, Any] = default_data()
        self.current_path: str | None = None
        self.is_dirty: bool = False

    def set_data(self, new_data: Dict[str, Any], path: str | None = None) -> None:
        self.data = new_data if isinstance(new_data, dict) else default_data()
        self.current_path = path
        self.set_dirty(False)  # Charger = pas dirty
        self.dataChanged.emit()

    def set_dirty(self, value: bool) -> None:
        value = bool(value)
        if self.is_dirty == value:
            return
        self.is_dirty = value
        self.dirtyChanged.emit(self.is_dirty)

    def mark_dirty(self) -> None:
        self.set_dirty(True)

    # =========================================================
    # Referential integrity helpers (rename + propagation)
    # =========================================================

    def _emit_changed(self) -> None:
        """Marque dirty + rafraîchit toutes les pages (dataChanged)."""
        self.mark_dirty()
        self.dataChanged.emit()

    def _iter_all_posts(self):
        """
        Itère sur tous les posts (public profiles + heroine).
        Yields: post_dict
        """
        profiles = self.data.get("profiles", {}) or {}
        for _, prof in profiles.items():
            posts = (prof or {}).get("posts", {}) or {}
            for _, post in posts.items():
                if isinstance(post, dict):
                    yield post

        heroine = self.data.get("heroine", {}) or {}
        h_posts = heroine.get("posts", {}) or {}
        for _, post in h_posts.items():
            if isinstance(post, dict):
                yield post

    def rename_username_pool(self, old: str, new: str) -> bool:
        """
        Renomme usernames[old] -> usernames[new] ET met à jour
        commentBlocks[*].usernamePool.
        """
        old = (old or "").strip()
        new = (new or "").strip()
        if not old or not new or old == new:
            return False

        pools = self.data.setdefault("usernames", {})
        if old not in pools:
            return False
        if new in pools:
            return False

        pools[new] = pools.pop(old)

        blocks = self.data.get("commentBlocks", {}) or {}
        for _, b in blocks.items():
            if isinstance(b, dict) and b.get("usernamePool") == old:
                b["usernamePool"] = new

        self._emit_changed()
        return True

    def rename_comment_set(self, old: str, new: str) -> bool:
        """
        Renomme commentSets[old] -> commentSets[new] ET met à jour
        posts[*].commentsSet (public + heroine).
        """
        old = (old or "").strip()
        new = (new or "").strip()
        if not old or not new or old == new:
            return False

        sets_ = self.data.setdefault("commentSets", {})
        if old not in sets_:
            return False
        if new in sets_:
            return False

        sets_[new] = sets_.pop(old)

        for post in self._iter_all_posts():
            if post.get("commentsSet") == old:
                post["commentsSet"] = new

        self._emit_changed()
        return True

    def rename_emoji_preset(self, old: str, new: str) -> bool:
        """
        Renomme emojiPresets[old] -> emojiPresets[new] ET met à jour
        posts[*].emojiPreset (public + heroine).
        """
        old = (old or "").strip()
        new = (new or "").strip()
        if not old or not new or old == new:
            return False

        presets = self.data.setdefault("emojiPresets", {})
        if old not in presets:
            return False
        if new in presets:
            return False

        presets[new] = presets.pop(old)

        for post in self._iter_all_posts():
            if post.get("emojiPreset") == old:
                post["emojiPreset"] = new

        self._emit_changed()
        return True

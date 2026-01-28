# Software/validators.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List


@dataclass(frozen=True)
class Issue:
    level: str   # "ERROR" | "WARN" | "INFO"
    path: str    # ex: "profiles.CatElf.posts.Breakfast.commentsSet"
    message: str


def _is_non_empty_str(x: Any) -> bool:
    return isinstance(x, str) and x.strip() != ""


def _iter_all_posts(data: Dict[str, Any]) -> Iterable[tuple[str, Dict[str, Any]]]:
    """Yield (path_prefix, post_dict) for all posts (profiles + heroine)."""
    profiles = data.get("profiles", {}) or {}
    if isinstance(profiles, dict):
        for profile_id, prof in profiles.items():
            if not isinstance(prof, dict):
                continue
            posts = (prof.get("posts", {}) or {})
            if not isinstance(posts, dict):
                continue
            for post_key, post in posts.items():
                if isinstance(post, dict):
                    yield (f"profiles.{profile_id}.posts.{post_key}", post)

    heroine = data.get("heroine", {}) or {}
    if isinstance(heroine, dict):
        h_posts = (heroine.get("posts", {}) or {})
        if isinstance(h_posts, dict):
            for post_key, post in h_posts.items():
                if isinstance(post, dict):
                    yield (f"heroine.posts.{post_key}", post)


def validate_database(data: Dict[str, Any]) -> List[Issue]:
    issues: List[Issue] = []

    usernames = data.get("usernames", {}) or {}
    comment_blocks = data.get("commentBlocks", {}) or {}
    comment_sets = data.get("commentSets", {}) or {}
    emoji_presets = data.get("emojiPresets", {}) or {}

    # --- Types de base
    if not isinstance(usernames, dict):
        issues.append(Issue("ERROR", "usernames", "Doit être un dictionnaire (poolId -> [names])."))
        usernames = {}

    if not isinstance(comment_blocks, dict):
        issues.append(Issue("ERROR", "commentBlocks", "Doit être un dictionnaire (blockId -> block)."))
        comment_blocks = {}

    if not isinstance(comment_sets, dict):
        issues.append(Issue("ERROR", "commentSets", "Doit être un dictionnaire (setId -> [blockIds])."))
        comment_sets = {}

    if not isinstance(emoji_presets, dict):
        issues.append(Issue("ERROR", "emojiPresets", "Doit être un dictionnaire (presetId -> preset)."))
        emoji_presets = {}

    # --- usernames pools: list[str]
    for pool_id, names in usernames.items():
        p = f"usernames.{pool_id}"
        if not isinstance(names, list):
            issues.append(Issue("ERROR", p, "Doit être une liste de strings."))
            continue
        for i, n in enumerate(names):
            if not _is_non_empty_str(n):
                issues.append(Issue("WARN", f"{p}[{i}]", "Nom vide ou non-string."))

    # --- commentBlocks -> usernames pool
    for block_id, block in comment_blocks.items():
        p = f"commentBlocks.{block_id}"
        if not isinstance(block, dict):
            issues.append(Issue("ERROR", p, "Block doit être un dict."))
            continue
        pool = block.get("usernamePool", "")
        if _is_non_empty_str(pool) and pool not in usernames:
            issues.append(Issue("ERROR", f"{p}.usernamePool", f"Pool '{pool}' introuvable dans usernames."))

    # --- commentSets -> commentBlocks
    for set_id, block_ids in comment_sets.items():
        p = f"commentSets.{set_id}"
        if not isinstance(block_ids, list):
            issues.append(Issue("ERROR", p, "Doit être une liste de blockId."))
            continue
        for i, bid in enumerate(block_ids):
            if not _is_non_empty_str(bid):
                issues.append(Issue("WARN", f"{p}[{i}]", "Référence blockId vide ou non-string."))
                continue
            if bid not in comment_blocks:
                issues.append(Issue("ERROR", f"{p}[{i}]", f"BlockId '{bid}' introuvable dans commentBlocks."))

    # --- posts -> emojiPreset / commentsSet
    for post_path, post in _iter_all_posts(data):
        ep = post.get("emojiPreset", "")
        cs = post.get("commentsSet", "")

        if _is_non_empty_str(ep) and ep not in emoji_presets:
            issues.append(Issue("ERROR", f"{post_path}.emojiPreset", f"Preset '{ep}' introuvable dans emojiPresets."))

        if _is_non_empty_str(cs) and cs not in comment_sets:
            issues.append(Issue("ERROR", f"{post_path}.commentsSet", f"Set '{cs}' introuvable dans commentSets."))

    return issues

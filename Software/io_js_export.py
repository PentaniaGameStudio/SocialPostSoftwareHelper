# io_js_export.py
from __future__ import annotations
import re
import json
from typing import Any, Dict


def export_to_js(data: Dict[str, Any]) -> str:
    """
    Exporte un plugin "data-only" pour RPG Maker MZ.
    Objectif: efficience (pas de duplication) :
    - Les posts référencent un commentsSetId au lieu d'embarquer les commentaires.
    - Les posts référencent un emojiPresetId au lieu d'embarquer les valeurs, sauf si preset == "" (custom).
    """
    # Debug/guard: on veut un dict à la racine
    if not isinstance(data, dict):
        raise TypeError(f"export_to_js: data doit être un dict, reçu {type(data).__name__}")

    # ─────────────────────────────────────────────────────────────
    # Récupération des blocs depuis le JSON du software
    # ─────────────────────────────────────────────────────────────
    profiles = data.get("profiles", {}) or {}
    heroine = data.get("heroine", {"posts": {}}) or {"posts": {}}

    usernames = data.get("usernames", {}) or {}
    comment_blocks = data.get("commentBlocks", {}) or {}
    comment_sets = data.get("commentSets", {}) or {}
    emoji_presets = data.get("emojiPresets", {}) or {}

    # ─────────────────────────────────────────────────────────────
    # Normalisation / nettoyage
    # ─────────────────────────────────────────────────────────────

    # On enlève "order" (utile uniquement pour l'éditeur)
    cleaned_emoji_presets: Dict[str, Any] = {}
    for preset_id in sorted(emoji_presets.keys()):
        preset = dict(emoji_presets.get(preset_id) or {})
        preset.pop("order", None)
        cleaned_emoji_presets[preset_id] = preset

    # CommentBlocks: accepte plusieurs formats (robuste legacy)
    # Format attendu (éditeur):
    #   {"blockId": {"usernamePool": "Global", "comments": ["...", "..."]}}
    # Formats legacy possibles:
    #   {"blockId": ["...", "..."]}  (liste de texts, pool=Global)
    cleaned_comment_blocks: Dict[str, Any] = {}
    for block_id in sorted(comment_blocks.keys()):
        b = comment_blocks.get(block_id)

        if isinstance(b, dict):
            pool_id = (b.get("usernamePool", "Global") or "Global")
            texts = b.get("comments", []) or []
        elif isinstance(b, list):
            pool_id = "Global"
            texts = b
        else:
            pool_id = "Global"
            texts = []

        # Normalise en { poolId, texts }
        cleaned_comment_blocks[block_id] = {
            "usernamePool": str(pool_id),
            "texts": list(texts),
        }


    # CommentSets: accepte 2 formats:
    # - {"SetId": {"blocks": [...]}}
    # - {"SetId": [...]}
    cleaned_comment_sets: Dict[str, Any] = {}
    for set_id in sorted(comment_sets.keys()):
        s = comment_sets.get(set_id)

        if isinstance(s, list):
            blocks = s
        elif isinstance(s, dict):
            blocks = s.get("blocks", []) or []
        else:
            blocks = []

        cleaned_comment_sets[set_id] = list(blocks)



    # Posts: optimisation emoji (custom inline, preset par id)
    def _export_post(post: Dict[str, Any]) -> Dict[str, Any]:
        p = dict(post or {})

        out: Dict[str, Any] = {
            "pictureName": p.get("pictureName", "") or "",
            "description": p.get("description", "") or "",
            "timeslot": _clean_timeslot(p.get("timeslot", "all")),
            "conditionJS": p.get("conditionJS", "") or "",
            "effectJs": p.get("effectJs", "") or "",
            "commentsSetId": p.get("commentsSet", "") or "",
            "lewdCondition": p.get("lewdCondition", {"min": 0, "max": 999999}) or {"min": 0, "max": 999999},
        }

        preset_id = (p.get("emojiPreset", "") or "").strip()
        if preset_id:
            # preset => référence uniquement
            out["emojiPresetId"] = preset_id
        else:
            # custom => inline
            out["emoji"] = p.get("emojiOverride", _default_emoji()) or _default_emoji()

        return out

    # Social Profiles (public)
    exported_profiles: Dict[str, Any] = {}
    for profile_id in sorted(profiles.keys()):
        prof = profiles.get(profile_id) or {}
        posts = prof.get("posts", {}) or {}

        exported_posts: Dict[str, Any] = {}
        for post_id in sorted(posts.keys()):
            exported_posts[post_id] = _export_post(posts[post_id] or {})

        exported_profiles[profile_id] = {
            "defaultDisplayName": prof.get("defaultDisplayName", "") or "",
            "defaultProfileImage": prof.get("defaultProfileImage", "") or "",
            "posts": exported_posts,
        }

    # Heroine Profile (unique)
    heroine_posts = heroine.get("posts", {}) or {}
    exported_heroine_posts: Dict[str, Any] = {}
    for post_id in sorted(heroine_posts.keys()):
        exported_heroine_posts[post_id] = _export_post(heroine_posts[post_id] or {})

    exported_heroine = {
        "defaultDisplayName": heroine.get("defaultDisplayName", "") or "",
        "defaultProfileImage": heroine.get("defaultProfileImage", "") or "",
        "posts": exported_heroine_posts,
    }

    # ─────────────────────────────────────────────────────────────
    # Construction du JS (stable + lisible)
    # ─────────────────────────────────────────────────────────────
    username_pools_js = _export_username_pools(usernames)

    # Dumps JSON (sans ASCII, stable)
    def dumps(obj: Any) -> str:
        return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True)

    blocks_js = dumps(cleaned_comment_blocks)
    sets_js = dumps(cleaned_comment_sets)
    emoji_js = dumps(cleaned_emoji_presets)
    profiles_js = dumps(exported_profiles)
    heroine_js = dumps(exported_heroine)

    # Header + helpers (on garde makeComments/makeFinalComments, utiles côté runtime)
    return f"""/*:
 * @target MZ
 * @plugindesc [data-only] Social Data (export)
 * @author Naughty Arcade
 * @help
 * Généré automatiquement par le Social Post Software.
 * Doit être placé AVANT le plugin runtime (NAS_SocialHelper_MZ).
 */

(() => {{
  // Namespace global NAS (si pas déjà créé)
  window.NAS = window.NAS || {{}};

  // ─────────────────────────────────────────────────────────────
  // Helpers: commentaires
  // ─────────────────────────────────────────────────────────────
  function makeComments(texts, poolId = "Global") {{
    return (texts || []).map(text => ({{
      authorMode: "randomFromPool",
      poolId,
      fixedAuthor: "",
      text
    }}));
  }}

  function makeFinalComments(...groups) {{
    return groups.reduce((acc, group) => {{
      if (Array.isArray(group) && group.length > 0) {{
        acc.push(...group);
      }}
      return acc;
    }}, []);
  }}

  // ─────────────────────────────────────────────────────────────
  // Data: username pools (Map)
  // ─────────────────────────────────────────────────────────────
  const COMMENT_USERNAME_POOLS = {username_pools_js};

  // ─────────────────────────────────────────────────────────────
  // Data: comments blocks/sets (références, pas de duplication)
  // ─────────────────────────────────────────────────────────────
  const SOCIAL_COMMENT_BLOCKS = {blocks_js};

  const SOCIAL_COMMENT_SETS = {sets_js};

  // ─────────────────────────────────────────────────────────────
  // Data: emojis presets (références, pas de duplication)
  // ─────────────────────────────────────────────────────────────
  const SOCIAL_EMOJI_PRESETS = {emoji_js};

  // ─────────────────────────────────────────────────────────────
  // Data: profiles
  // ─────────────────────────────────────────────────────────────
  const SOCIAL_PROFILES = {profiles_js};

  const SOCIAL_HEROINE_PROFILE = {heroine_js};

  // ─────────────────────────────────────────────────────────────
  // Exposition dans le namespace NAS
  // ─────────────────────────────────────────────────────────────
  NAS.COMMENT_USERNAME_POOLS = COMMENT_USERNAME_POOLS;

  NAS.SOCIAL_COMMENT_BLOCKS = SOCIAL_COMMENT_BLOCKS;
  NAS.SOCIAL_COMMENT_SETS = SOCIAL_COMMENT_SETS;

  NAS.SOCIAL_EMOJI_PRESETS = SOCIAL_EMOJI_PRESETS;

  NAS.SOCIAL_PROFILES = SOCIAL_PROFILES;
  NAS.SOCIAL_HEROINE_PROFILE = SOCIAL_HEROINE_PROFILE;

  // (Optionnel) exposer les helpers si ton runtime en a besoin
  NAS._makeComments = makeComments;
  NAS._makeFinalComments = makeFinalComments;

}})();
"""

def _clean_timeslot(value: str) -> str:
    if not value:
        return "all"

    # Supprime emojis et caractères non utiles
    # (on garde lettres, chiffres, underscore, tiret)
    value = re.sub(r"[^\w\-]", "", value, flags=re.UNICODE)

    value = value.strip().lower()
    return value or "all"

def _default_emoji() -> Dict[str, Any]:
    return {
        "up": {"min": 0, "max": 0},
        "down": {"min": 0, "max": 0},
        "heart": {"min": 0, "max": 0},
        "comment": {"min": 0, "max": 0},
    }


def _export_username_pools(pools: dict) -> str:
    """
    Transforme { "Global": [..], "CatLover": [..] }
    → new Map([ ["Global", [...]], ... ])
    """
    lines = []
    for key in sorted((pools or {}).keys()):
        values = pools.get(key) or []
        arr = json.dumps(values, ensure_ascii=False)
        lines.append(f'    ["{key}", {arr}]')

    return "new Map([\n" + ",\n".join(lines) + "\n  ])"

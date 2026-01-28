from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ThemeManager:
    """
    Gère le thème Qt-Material.
    On stocke un nom de fichier xml (ex: 'dark_teal.xml').
    """
    # Liste "safe" que tu peux adapter selon ton install qt-material
    themes_dark: list[str] = None
    themes_light: list[str] = None

    is_dark: bool = True
    theme_index: int = 0

    def __post_init__(self) -> None:
        if self.themes_dark is None:
            self.themes_dark = [
                "dark_teal.xml",
                "dark_blue.xml",
                "dark_amber.xml",
                "dark_cyan.xml",
                "dark_purple.xml",
            ]
        if self.themes_light is None:
            self.themes_light = [
                "light_teal.xml",
                "light_blue.xml",
                "light_amber.xml",
                "light_cyan.xml",
                "light_purple.xml",
            ]

    def current_theme_file(self) -> str:
        themes = self.themes_dark if self.is_dark else self.themes_light
        idx = max(0, min(self.theme_index, len(themes) - 1))
        return themes[idx]

    def set_dark(self, value: bool) -> None:
        self.is_dark = bool(value)

    def set_theme_index(self, idx: int) -> None:
        self.theme_index = int(idx)

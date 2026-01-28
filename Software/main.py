from PySide6.QtWidgets import QApplication
from qt_material import apply_stylesheet

from app_window import AppWindow
from theme_manager import ThemeManager


def main() -> None:
    app = QApplication([])

    # Theme manager central (dark/light + couleur)
    theme = ThemeManager()
    apply_stylesheet(app, theme=theme.current_theme_file())

    w = AppWindow(app=app, theme=theme)
    w.show()

    app.exec()


if __name__ == "__main__":
    main()

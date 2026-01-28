import sys
from pathlib import Path
import runpy


def main():
    # Dossier racine (là où est Start.pyw)
    root = Path(__file__).resolve().parent

    # Chemin vers Software/main.py
    main_py = root / "Software" / "main.py"

    if not main_py.exists():
        raise FileNotFoundError(f"main.py introuvable : {main_py}")

    # Ajoute Software au PYTHONPATH
    sys.path.insert(0, str(main_py.parent))

    # Lance main.py comme script principal
    runpy.run_path(str(main_py), run_name="__main__")


if __name__ == "__main__":
    main()

"""Сборка exe и установщика.

    venv\\Scripts\\python.exe build_exe.py               # только exe
    venv\\Scripts\\python.exe build_exe.py --installer   # exe + setup.exe

Требуется PyInstaller (pip install pyinstaller). Для установщика —
Inno Setup 6 (ISCC.exe).
"""

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(ROOT, "dist")
NAME = "EVE LangBridge"
ICON_SIZES = [16, 24, 32, 48, 64, 128, 256]

ISCC_CANDIDATES = [
    r"C:\Program Files\Inno Setup 7\ISCC.exe",
    r"C:\Program Files (x86)\Inno Setup 7\ISCC.exe",
    r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    r"C:\Program Files\Inno Setup 6\ISCC.exe",
    os.path.join(os.environ.get("LOCALAPPDATA", ""),
                 r"Programs\Inno Setup 7\ISCC.exe"),
    os.path.join(os.environ.get("LOCALAPPDATA", ""),
                 r"Programs\Inno Setup 6\ISCC.exe"),
]


def version():
    sys.path.insert(0, ROOT)
    from version import VERSION
    return VERSION


def make_icon():
    """assets/app.ico — из той же пиксельной сетки, что и иконка в окне."""
    sys.path.insert(0, ROOT)
    from app_icon import make_pil_image

    assets = os.path.join(ROOT, "assets")
    os.makedirs(assets, exist_ok=True)
    path = os.path.join(assets, "app.ico")
    make_pil_image(256).save(
        path, format="ICO", sizes=[(size, size) for size in ICON_SIZES])
    print("icon:", path)
    return path


def build_exe():
    icon = make_icon()
    command = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--windowed",
        "--name", NAME,
        "--icon", icon,
        "--collect-all", "customtkinter",
        "--hidden-import", "pystray._win32",
        "--hidden-import", "PIL.ImageTk",
        "--hidden-import", "PIL._tkinter_finder",        "--add-data", os.path.join(ROOT, "eve_terms.json") + ";.",
        "--add-data", os.path.join(ROOT, "slang.json") + ";.",
        "--add-data", os.path.join(ROOT, "icons", "logo-100.png") + ";icons",
        "--add-data", os.path.join(ROOT, "icons", "logo-64.png") + ";icons",
        "--add-data", os.path.join(ROOT, "icons", "logo-32.png") + ";icons",
        "--add-data", os.path.join(ROOT, "icons", "logo-16.png") + ";icons",
        os.path.join(ROOT, "main.py"),
    ]
    result = subprocess.run(command, cwd=ROOT)
    print("PyInstaller exit code:", result.returncode)
    if result.returncode != 0:
        raise SystemExit(result.returncode)
    exe = os.path.join(DIST, NAME, NAME + ".exe")
    if not os.path.exists(exe):
        raise SystemExit("exe не собрался: " + exe)
    print("exe:", exe)
    return exe


def find_iscc():
    for path in ISCC_CANDIDATES:
        if os.path.exists(path):
            return path
    from shutil import which
    return which("ISCC")


def build_installer():
    iscc = find_iscc()
    if not iscc:
        print("Inno Setup (ISCC.exe) не найден — установщик пропущен.")
        return None
    subprocess.check_call(
        [iscc, f"/DAppVersion={version()}",
         os.path.join(ROOT, "installer.iss")],
        cwd=ROOT,
    )
    setup = os.path.join(DIST, f"EVE-LangBridge-{version()}-setup.exe")
    print("installer:", setup if os.path.exists(setup) else "не найден")
    return setup


if __name__ == "__main__":
    build_exe()
    if "--installer" in sys.argv:
        build_installer()

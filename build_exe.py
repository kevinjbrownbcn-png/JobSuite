#!/usr/bin/env python3
"""
build_exe.py — One-click builder for JobSuite .exe
====================================================
Packages launch_launcher.py + all HTML/JS/CSS/icon files into a
standalone Windows executable using PyInstaller.

config.json is intentionally NOT bundled — it stays next to the .exe
so you can update API keys and webhook URLs without rebuilding.

Requirements (install once):
    pip install pyinstaller pywebview

Usage:
    python build_exe.py              # folder output (fast startup, default)
    python build_exe.py --onefile    # single .exe (easier to share)
    python build_exe.py --debug      # keep console window for troubleshooting
    python build_exe.py --debug-app  # bake DevTools (F12) into the .exe

Output:
    dist/JobSuite/JobSuite.exe   (--onedir, default)
    dist/JobSuite.exe            (--onefile)
"""

import argparse
import os
import shutil
import subprocess
import sys

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
APP_NAME    = "JobSuite"
SCRIPT_FILE = "launch_launcher.py"
ICON_FILE   = "launcher.ico"
CONFIG_FILE = "config.json"       # kept EXTERNAL — never bundled
# ---------------------------------------------------------------------------

# Files and folders to exclude from the bundle
EXCLUDE_NAMES = {"config.json", "__pycache__", "build", "dist", "logs", ".git", ".gitignore"}
EXCLUDE_EXTS  = {".py", ".spec", ".pyc"}


def find_file(filename: str, base_dir: str) -> str:
    path = os.path.join(base_dir, filename)
    if not os.path.isfile(path):
        print(f"\n[ERROR] Required file not found: {path}")
        print(f"  Make sure '{filename}' is in the same folder as this build script.\n")
        sys.exit(1)
    return path


def check_pyinstaller() -> None:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print(
            "\n[ERROR] PyInstaller is not installed.\n"
            "Install it with:\n\n"
            "    pip install pyinstaller\n"
        )
        sys.exit(1)


def _force_remove(path: str) -> None:
    import stat
    import time

    def _on_error(func, failing_path, exc_info):
        try:
            os.chmod(failing_path, stat.S_IWRITE)
            func(failing_path)
        except Exception:
            pass

    for attempt in range(3):
        try:
            if os.path.isfile(path):
                os.chmod(path, stat.S_IWRITE)
                os.remove(path)
            elif os.path.isdir(path):
                shutil.rmtree(path, onexc=_on_error)
            return
        except PermissionError as exc:
            if attempt < 2:
                print(f"[CLEAN] Locked — retrying in 2s ({exc.filename})")
                time.sleep(2)
            else:
                print(f"[CLEAN] WARNING: Could not delete {path}")
                print(f"         Reason : {exc}")
                print(f"         Fix    : close the app / pause OneDrive, then rebuild.")


def clean_build_artifacts(base_dir: str) -> None:
    removed = []
    skipped = []

    for folder in ("build", "dist"):
        target = os.path.join(base_dir, folder)
        if os.path.isdir(target):
            _force_remove(target)
            removed.append(folder + "/")
        else:
            skipped.append(folder + "/")

    spec = os.path.join(base_dir, f"{APP_NAME}.spec")
    if os.path.isfile(spec):
        _force_remove(spec)
        removed.append(f"{APP_NAME}.spec")
    else:
        skipped.append(f"{APP_NAME}.spec")

    pycache = os.path.join(base_dir, "__pycache__")
    if os.path.isdir(pycache):
        _force_remove(pycache)
        removed.append("__pycache__/")
    else:
        skipped.append("__pycache__/")

    hook = os.path.join(base_dir, "_debug_hook.py")
    if os.path.isfile(hook):
        _force_remove(hook)
        removed.append("_debug_hook.py")

    if removed:
        print(f"[CLEAN] Deleted : {', '.join(removed)}")
    if skipped:
        print(f"[CLEAN] Not found (skipped): {', '.join(skipped)}")


def copy_config_next_to_exe(base_dir: str, onefile: bool) -> None:
    src = os.path.join(base_dir, CONFIG_FILE)
    if not os.path.isfile(src):
        return

    dest_dir = os.path.join(base_dir, "dist") if onefile else os.path.join(base_dir, "dist", APP_NAME)
    dest = os.path.join(dest_dir, CONFIG_FILE)
    if os.path.isdir(dest_dir):
        shutil.copy2(src, dest)
        print(f"[INFO] config.json copied to: {dest}")


def collect_add_data(base_dir: str) -> list:
    """
    Walk the JobSuite root and collect all non-excluded files.
    Each entry maps source path → destination inside the bundle (under src/).
    """
    entries = []

    for root, dirs, files in os.walk(base_dir):
        # Skip excluded directories in-place
        dirs[:] = [d for d in dirs if d not in EXCLUDE_NAMES and not d.startswith(".")]

        bundleable = [
            f for f in files
            if f not in EXCLUDE_NAMES
            and os.path.splitext(f)[1].lower() not in EXCLUDE_EXTS
        ]

        if not bundleable:
            continue

        rel  = os.path.relpath(root, base_dir)
        dest = os.path.join("src", rel).rstrip(".")
        dest = dest.rstrip(os.sep)

        # Add the whole folder (PyInstaller copies all matching files)
        entries.append(f"{root}{os.pathsep}{dest}")

    return entries


def build(onefile: bool, debug: bool, base_dir: str, debug_app: bool = False) -> None:
    script_path = find_file(SCRIPT_FILE, base_dir)

    add_data_entries = collect_add_data(base_dir)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", APP_NAME,
        "--noconfirm",
        "--clean",
        "--exclude-module", "config",
    ]

    for entry in add_data_entries:
        cmd += ["--add-data", entry]
        print(f"[INFO] Bundling: {entry}")

    if onefile:
        cmd.append("--onefile")
    else:
        cmd.append("--onedir")

    if not debug:
        cmd.append("--noconsole")

    if debug_app:
        hook_path = os.path.join(base_dir, "_debug_hook.py")
        with open(hook_path, "w") as hf:
            hf.write("import os\nos.environ['PYWEBVIEW_DEBUG'] = '1'\n")
        cmd += ["--runtime-hook", hook_path]
        print("[INFO] DevTools (F12) will be enabled in the compiled .exe")

    icon_path = os.path.join(base_dir, ICON_FILE)
    if os.path.isfile(icon_path):
        print(f"[INFO] Using icon: {icon_path}")
        cmd += ["--icon", icon_path]
    else:
        print(f"[INFO] Icon not found ({ICON_FILE}) — using default PyInstaller icon.")

    cmd.append(script_path)

    print("\n[INFO] Running PyInstaller...")
    print("  " + " ".join(cmd) + "\n")

    result = subprocess.run(cmd, cwd=base_dir)

    if result.returncode != 0:
        print("\n[ERROR] PyInstaller failed. See output above for details.\n")
        sys.exit(result.returncode)

    copy_config_next_to_exe(base_dir, onefile)

    if onefile:
        exe      = os.path.join(base_dir, "dist", f"{APP_NAME}.exe")
        cfg_dest = os.path.join(base_dir, "dist", CONFIG_FILE)
    else:
        out_dir  = os.path.join(base_dir, "dist", APP_NAME)
        exe      = os.path.join(out_dir, f"{APP_NAME}.exe")
        cfg_dest = os.path.join(out_dir, CONFIG_FILE)

    print(f"\n{'='*60}")
    print(f"  Build complete!")
    if not onefile:
        print(f"  Folder     : {out_dir}")
    print(f"  Executable : {exe}")
    print(f"  Config     : {cfg_dest}  <-- fill in your API keys before running")
    print(f"{'='*60}")
    print("\n  Keep config.json in the SAME FOLDER as the .exe.")
    print("  Do NOT share or commit config.json — it contains your keys.\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build JobSuite into a Windows .exe"
    )
    parser.add_argument(
        "--onefile",
        action="store_true",
        help="Pack everything into a single .exe (slower startup, easier to share)",
    )
    parser.add_argument(
        "--onedir",
        action="store_true",
        help="Output a folder with the .exe (faster startup, default)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Keep the console window open (useful for troubleshooting crashes)",
    )
    parser.add_argument(
        "--no-clean",
        action="store_true",
        help="Skip removing previous build/dist folders",
    )
    parser.add_argument(
        "--debug-app",
        action="store_true",
        help="Bake DevTools (F12) into the .exe — useful for testing a built version",
    )
    args = parser.parse_args()

    onefile  = args.onefile and not args.onedir
    base_dir = os.path.dirname(os.path.abspath(__file__))

    print(f"\n{'='*60}")
    print(f"  JobSuite — EXE Builder")
    print(f"{'='*60}")
    print(f"  Mode    : {'single .exe' if onefile else 'folder (onedir)'}")
    print(f"  Debug   : {'yes (console visible)' if args.debug else 'no'}")
    print(f"  DevTools: {'yes (F12 enabled in .exe)' if args.debug_app else 'no'}")
    print(f"  Base dir: {base_dir}\n")

    check_pyinstaller()

    if not args.no_clean:
        clean_build_artifacts(base_dir)

    build(onefile=onefile, debug=args.debug, base_dir=base_dir, debug_app=args.debug_app)


if __name__ == "__main__":
    main()

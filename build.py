"""Builds AuraGram into a standalone program and, when Inno Setup is installed, an installer.

    python build.py               tests, program, self-check, installer
    python build.py --skip-tests  the same without running the tests first

Results:
    dist/AuraGram/AuraGram.exe          the program with everything it needs beside it
    dist/AuraGram-Setup-<version>.exe   the installer

Needs PyInstaller (pip install pyinstaller). The installer step needs Inno Setup 6
(https://jrsoftware.org/isinfo.php) and is skipped with a notice if it is not found.
"""
import os
import shutil
import subprocess
import sys

from core.constants import APP_NAME, APP_VERSION, BASE_DIR, CHECK_FLAG

DIST_DIR = os.path.join(BASE_DIR, "dist")
WORK_DIR = os.path.join(BASE_DIR, "build")
PROGRAM = os.path.join(DIST_DIR, APP_NAME, APP_NAME + ".exe")
INSTALLER = os.path.join(DIST_DIR, "%s-Setup-%s.exe" % (APP_NAME, APP_VERSION))
# Read-only files the program loads at run time.
DATA_FOLDERS = ("locales", "assets")
# Packages whose DLLs and data files PyInstaller does not find from the imports
# alone: the screen reader bridges, the audio device library, and the codecs.
COLLECTED_PACKAGES = ("accessible_output2", "sounddevice", "av")
INNO_SETUP_COMPILERS = (
    os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Inno Setup 6", "ISCC.exe"),
    os.path.join(os.environ.get("ProgramFiles", ""), "Inno Setup 6", "ISCC.exe"),
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Inno Setup 6", "ISCC.exe"),
)
SELF_CHECK_PROBLEMS = (
    (1, "texts, icon or tones are missing from the build"),
    (2, "voice messages will not work (audio libraries not bundled)"),
    (4, "screen reader announcements will not work (accessible_output2 not bundled)"),
)


def step(title):
    print("\n=== %s ===" % title, flush=True)


def run(command):
    """Run a command, stopping the build if it fails."""
    result = subprocess.run(command, cwd=BASE_DIR)
    if result.returncode != 0:
        sys.exit("Build stopped: %s failed (exit code %d)." % (os.path.basename(command[0]), result.returncode))


def run_tests():
    step("Running the tests")
    run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."])


def build_program():
    step("Building the program with PyInstaller")
    # Start clean so files removed from the project do not linger in the build.
    shutil.rmtree(os.path.join(DIST_DIR, APP_NAME), ignore_errors=True)
    command = [
        sys.executable, "-m", "PyInstaller", os.path.join(BASE_DIR, "main.py"),
        "--name", APP_NAME, "--noconfirm", "--clean", "--windowed",
        "--icon", os.path.join(BASE_DIR, "assets", "auragram.ico"),
        "--distpath", DIST_DIR, "--workpath", WORK_DIR, "--specpath", WORK_DIR,
        "--exclude-module", "tests",
    ]
    for folder in DATA_FOLDERS:
        command += ["--add-data", os.path.join(BASE_DIR, folder) + os.pathsep + folder]
    for package in COLLECTED_PACKAGES:
        command += ["--collect-all", package]
    run(command)


def check_program():
    """Ask the built program itself whether its bundled pieces are all present."""
    step("Checking the built program")
    code = subprocess.run([PROGRAM, CHECK_FLAG]).returncode
    problems = [text for bit, text in SELF_CHECK_PROBLEMS if code & bit]
    if code and not problems:
        sys.exit("Build stopped: the program did not start (exit code %d)." % code)
    if code & 1:
        sys.exit("Build stopped: " + problems[0] + ".")
    for text in problems:
        print("WARNING:", text)
    if not problems:
        print("The program starts and has everything it needs.")


def build_installer():
    step("Building the installer with Inno Setup")
    compiler = next((path for path in INNO_SETUP_COMPILERS if os.path.exists(path)), None)
    if compiler is None:
        print("Inno Setup 6 was not found, so no installer was made.")
        print("Install it from https://jrsoftware.org/isinfo.php and run this script again.")
        return False
    run([compiler, "/Qp", "/DAppVersion=" + APP_VERSION, os.path.join(BASE_DIR, "installer.iss")])
    return True


def folder_size_mb(path):
    total = sum(
        os.path.getsize(os.path.join(root, name)) for root, _, names in os.walk(path) for name in names
    )
    return total / (1024 * 1024)


def main():
    if "--skip-tests" not in sys.argv:
        run_tests()
    build_program()
    check_program()
    has_installer = build_installer()

    step("Done")
    print("Program:   %s  (folder is %.0f MB)" % (PROGRAM, folder_size_mb(os.path.dirname(PROGRAM))))
    if has_installer:
        print("Installer: %s  (%.0f MB)" % (INSTALLER, os.path.getsize(INSTALLER) / (1024 * 1024)))


if __name__ == "__main__":
    main()

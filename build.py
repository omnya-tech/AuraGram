"""Builds AuraGram into a standalone program and, when Inno Setup is installed, an installer.

    python build.py               tests, program, self-check, installer
    python build.py --skip-tests  the same without running the tests first

Results:
    dist/AuraGram/AuraGram.exe          the program with everything it needs beside it
    dist/AuraGram-Setup-<version>.exe   the installer

Needs PyInstaller (pip install pyinstaller). The installer step needs Inno Setup 6
(https://jrsoftware.org/isinfo.php) and is skipped with a notice if it is not found.
"""
import json
import os
import shutil
import subprocess
import sys

from core.config import read_credentials, seal_credentials
from core.constants import (
    APP_COPYRIGHT, APP_NAME, APP_PUBLISHER, APP_VERSION, BASE_DIR, BUNDLED_CONFIG_NAME, CHECK_FLAG,
    CONFIG_FILE
)

DIST_DIR = os.path.join(BASE_DIR, "dist")
WORK_DIR = os.path.join(BASE_DIR, "build")
PROGRAM = os.path.join(DIST_DIR, APP_NAME, APP_NAME + ".exe")
INSTALLER = os.path.join(DIST_DIR, "%s-Setup-%s.exe" % (APP_NAME, APP_VERSION))
# Read-only files the program loads at run time.
DATA_FOLDERS = ("locales", "assets")
# Packages whose DLLs and data files PyInstaller does not find from the imports
# alone: the screen reader bridges, the audio device library, the codecs, and the
# SOCKS library Telethon loads only once a proxy is set.
COLLECTED_PACKAGES = ("accessible_output2", "sounddevice", "av", "python_socks")
INNO_SETUP_COMPILERS = (
    os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Inno Setup 6", "ISCC.exe"),
    os.path.join(os.environ.get("ProgramFiles", ""), "Inno Setup 6", "ISCC.exe"),
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Inno Setup 6", "ISCC.exe"),
)
VERSION_INFO_FILE = os.path.join(WORK_DIR, "version_info.txt")
# The format PyInstaller reads for a Windows version resource. 040904B0 = English, Unicode.
VERSION_INFO_TEMPLATE = """VSVersionInfo(
  ffi=FixedFileInfo(filevers={numbers}, prodvers={numbers}),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', '{publisher}'),
      StringStruct('LegalCopyright', '{copyright}'),
      StringStruct('FileDescription', '{name}'),
      StringStruct('ProductName', '{name}'),
      StringStruct('FileVersion', '{version}'),
      StringStruct('ProductVersion', '{version}'),
      StringStruct('OriginalFilename', '{name}.exe'),
    ])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""
SELF_CHECK_PROBLEMS = (
    (1, "texts, icon or tones are missing from the build"),
    (2, "voice messages will not work (audio libraries not bundled)"),
    (4, "screen reader announcements will not work (accessible_output2 not bundled)"),
    (8, "no API id and hash inside: the program will ask each user for them"),
    (16, "the built program could not connect to Telegram (no internet now, or a wrong API id)"),
)
BUNDLED_CONFIG_BUILD_FILE = os.path.join(WORK_DIR, BUNDLED_CONFIG_NAME)


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


def write_version_info():
    """Describe the program to Windows, so its Properties window shows the name and version."""
    numbers = tuple(int(part) for part in APP_VERSION.split(".")) + (0,)
    os.makedirs(WORK_DIR, exist_ok=True)
    with open(VERSION_INFO_FILE, "w", encoding="utf-8") as version_file:
        version_file.write(VERSION_INFO_TEMPLATE.format(
            numbers=numbers, name=APP_NAME, version=APP_VERSION,
            publisher=APP_PUBLISHER, copyright=APP_COPYRIGHT
        ))


def write_bundled_config():
    """Prepare the API id and hash that go inside the program, taken from this project's config.json.

    Only those two values are packed: never the session file, which is a login to
    one person's account. Returns False if the project has no usable config.json.
    """
    api_id, api_hash = read_credentials(CONFIG_FILE)
    if not api_id:
        print("NOTE: no valid config.json in the project, so the built program will ask")
        print("      every user for an API id and hash on first run.")
        return False
    os.makedirs(WORK_DIR, exist_ok=True)
    # Sealed: a search through the installed files finds neither value.
    with open(BUNDLED_CONFIG_BUILD_FILE, "wb") as config_file:
        config_file.write(seal_credentials(api_id, api_hash))
    print("Packing this project's API id and hash into the program, sealed.")
    return True


def build_program():
    step("Building the program with PyInstaller")
    # Start clean so files removed from the project do not linger in the build.
    shutil.rmtree(os.path.join(DIST_DIR, APP_NAME), ignore_errors=True)
    write_version_info()
    command = [
        sys.executable, "-m", "PyInstaller", os.path.join(BASE_DIR, "main.py"),
        "--name", APP_NAME, "--noconfirm", "--clean", "--windowed",
        "--icon", os.path.join(BASE_DIR, "assets", "auragram.ico"),
        "--version-file", VERSION_INFO_FILE,
        "--distpath", DIST_DIR, "--workpath", WORK_DIR, "--specpath", WORK_DIR,
        "--exclude-module", "tests",
    ]
    for folder in DATA_FOLDERS:
        command += ["--add-data", os.path.join(BASE_DIR, folder) + os.pathsep + folder]
    if write_bundled_config():
        command += ["--add-data", BUNDLED_CONFIG_BUILD_FILE + os.pathsep + "."]
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
    # The usual install folders first, then wherever the PATH knows an ISCC from.
    compiler = next((path for path in INNO_SETUP_COMPILERS if os.path.exists(path)), None) or shutil.which("ISCC")
    if compiler is None:
        print("Inno Setup 6 was not found, so no installer was made.")
        print("Install it from https://jrsoftware.org/isinfo.php and run this script again.")
        return False
    run([
        compiler, "/Qp", "/DAppVersion=" + APP_VERSION, "/DAppPublisher=" + APP_PUBLISHER,
        "/DAppCopyright=" + APP_COPYRIGHT, os.path.join(BASE_DIR, "installer.iss")
    ])
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

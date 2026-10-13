"""Builds AuraGram into a standalone program and, when Inno Setup is installed, an installer.

    python build.py               tests, program, self-check, installer
    python build.py --skip-tests  the same without running the tests first

Results:
    dist/AuraGram/AuraGram.exe          the program with everything it needs beside it
    dist/AuraGram-Setup-<version>.exe   the installer
    dist/AuraGram-Update-<version>.exe  the small installer for those who already have AuraGram
    dist/update.json                    what installed copies read to learn of this release

Needs PyInstaller (pip install pyinstaller). The installer step needs Inno Setup 6
(https://jrsoftware.org/isinfo.php) and is skipped with a notice if it is not found.
"""
import json
import os
import shutil
import subprocess
import sys

from core import updates
from core.config import read_credentials, seal_credentials
from core.constants import (
    APP_COPYRIGHT, APP_NAME, APP_PUBLISHER, APP_VERSION, BASE_DIR, BUNDLED_CONFIG_NAME, CHECK_FLAG,
    CONFIG_FILE, LEGAL_FILE_NAMES, PACKAGE_FILE_FORMATS, PACKAGE_FULL, PACKAGE_UPDATE, RELEASES_URL,
    UPDATE_BASE_VERSION, UPDATE_INFO_FILE_NAME, LANGUAGES
)

DIST_DIR = os.path.join(BASE_DIR, "dist")
WORK_DIR = os.path.join(BASE_DIR, "build")
PROGRAM = os.path.join(DIST_DIR, APP_NAME, APP_NAME + ".exe")
PACKAGES = {
    kind: os.path.join(DIST_DIR, name.format(version=APP_VERSION)) for kind, name in PACKAGE_FILE_FORMATS.items()
}
INSTALLER = PACKAGES[PACKAGE_FULL]
UPDATE_INFO_FILE = os.path.join(DIST_DIR, UPDATE_INFO_FILE_NAME)
# Stands where an address goes until RELEASES_URL in core/constants.py is set.
ADDRESS_TO_FILL_IN = "https://REPLACE-WITH-THE-RELEASES-ADDRESS"
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
    (1, "texts, icon, tones or the licence files are missing from the build"),
    (2, "voice messages will not work (audio libraries not bundled)"),
    (4, "screen reader announcements will not work (accessible_output2 not bundled)"),
    (8, "no API id and hash inside: the program will ask each user for them"),
    (16, "the built program could not connect to Telegram (no internet now, or a wrong API id)"),
)
BUNDLED_CONFIG_BUILD_FILE = os.path.join(WORK_DIR, BUNDLED_CONFIG_NAME)
# The secret half of the seal on the API id and hash: made anew by every build, compiled into
# that build's program, and kept out of git. See _build_secret in core/config.py.
SEAL_MODULE = "core._seal"
SEAL_MODULE_FILE = os.path.join(BASE_DIR, "core", "_seal.py")
SEAL_SECRET_BYTES = 32


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
    secret = os.urandom(SEAL_SECRET_BYTES)
    with open(SEAL_MODULE_FILE, "w", encoding="utf-8") as seal_file:
        seal_file.write("# Made by build.py for one build. Never commit this file.\nSECRET = %r\n" % secret)
    # Sealed: a search through the installed files finds neither value.
    with open(BUNDLED_CONFIG_BUILD_FILE, "wb") as config_file:
        config_file.write(seal_credentials(api_id, api_hash, secret))
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
    # wx's own words for its ready-made buttons, in each interface language that is not English.
    import wx
    for language in LANGUAGES:
        catalog = os.path.join(os.path.dirname(wx.__file__), "locale", language, "LC_MESSAGES", "wxstd.mo")
        if os.path.exists(catalog):
            command += ["--add-data", catalog + os.pathsep + os.path.join("wx", "locale", language, "LC_MESSAGES")]
    # The terms of use and the notices, for the Help menu to show.
    for name in LEGAL_FILE_NAMES:
        command += ["--add-data", os.path.join(BASE_DIR, name) + os.pathsep + "."]
    if write_bundled_config():
        command += ["--add-data", BUNDLED_CONFIG_BUILD_FILE + os.pathsep + ".", "--hidden-import", SEAL_MODULE]
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
    # The whole installer, then the small one that only brings an installed copy up to date.
    for extra in ([], ["/DUpdateOnly=1"]):
        run([
            compiler, "/Qp", "/DAppVersion=" + APP_VERSION, "/DAppPublisher=" + APP_PUBLISHER,
            "/DAppCopyright=" + APP_COPYRIGHT, *extra, os.path.join(BASE_DIR, "installer.iss")
        ])
    return True


def write_update_info():
    """Describe this release for the copies already installed: what to fetch and how to know it came whole.

    Upload the two installers to the release, write its notes into the file, and put
    the file where UPDATE_INFO_URL points.
    """
    step("Writing " + UPDATE_INFO_FILE_NAME)
    releases = RELEASES_URL.rstrip("/") or ADDRESS_TO_FILL_IN
    tag = "v" + APP_VERSION
    info = {
        "version": APP_VERSION,
        "url": "%s/tag/%s" % (releases, tag),
        "notes": {language: "" for language in LANGUAGES},
    }
    for kind, path in PACKAGES.items():
        info[kind] = updates.describe_file(path, "%s/download/%s/%s" % (releases, tag, os.path.basename(path)))
    info[PACKAGE_UPDATE]["from"] = UPDATE_BASE_VERSION
    with open(UPDATE_INFO_FILE, "w", encoding="utf-8") as info_file:
        json.dump(info, info_file, ensure_ascii=False, indent=4)
        info_file.write("\n")
    if not RELEASES_URL:
        print("NOTE: RELEASES_URL is not set in core/constants.py, so the addresses in the file")
        print("      are placeholders. Set it, or write the real addresses in by hand.")


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
    if has_installer:
        write_update_info()

    step("Done")
    print("Program:   %s  (folder is %.0f MB)" % (PROGRAM, folder_size_mb(os.path.dirname(PROGRAM))))
    if has_installer:
        print("Installer: %s  (%.0f MB)" % (INSTALLER, os.path.getsize(INSTALLER) / (1024 * 1024)))
        update = PACKAGES[PACKAGE_UPDATE]
        print("Update:    %s  (%.0f MB)" % (update, os.path.getsize(update) / (1024 * 1024)))
        print("Release:   %s" % UPDATE_INFO_FILE)


if __name__ == "__main__":
    main()

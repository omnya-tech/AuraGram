"""Builds AuraGram into a standalone program and, when Inno Setup is installed, an installer.

    python build.py               tests, program, self-check, installer
    python build.py --skip-tests  the same without running the tests first

    python build.py --sign-update  sign dist/update.json again, after changing it by hand
    python build.py --make-signing-key  make the release key, once (see core/signing.py)

Results:
    dist/AuraGram/AuraGram.exe          the program with everything it needs beside it
    dist/AuraGram-Setup-<version>.exe   the installer
    dist/AuraGram-Update-<version>.exe  the small installer for those who already have AuraGram
    dist/update.json                    what installed copies read to learn of this release, signed

Where a certificate is set up (SIGN_CERTIFICATE_ENV), the program and both installers are also signed
with it (Authenticode), so Windows names the publisher instead of warning of an unknown one.

Needs PyInstaller (pip install pyinstaller). The installer step needs Inno Setup 6 or 7
(https://jrsoftware.org/isinfo.php) and is skipped with a notice if it is not found.
"""
import json
import os
import shutil
import subprocess
import sys

from core import signing, updates
from core.config import pack_credentials, read_credentials
from core.constants import (
    APP_COPYRIGHT, APP_NAME, APP_PUBLISHER, APP_VERSION, BASE_DIR, BUNDLED_CONFIG_NAME, CHECK_FLAG,
    CONFIG_FILE, LEGAL_FILE_NAMES, PACKAGE_FILE_FORMATS, PACKAGE_FULL, PACKAGE_UPDATE, RELEASES_URL,
    UPDATE_BASE_VERSION, UPDATE_INFO_FILE_NAME, LANGUAGES
)

DIST_DIR = os.path.join(BASE_DIR, "dist")
WORK_DIR = os.path.join(BASE_DIR, "build")
# What the tests printed in the last build.
TESTS_LOG_FILE = os.path.join(WORK_DIR, "tests.log")
PROGRAM = os.path.join(DIST_DIR, APP_NAME, APP_NAME + ".exe")
PACKAGES = {
    kind: os.path.join(DIST_DIR, name.format(version=APP_VERSION)) for kind, name in PACKAGE_FILE_FORMATS.items()
}
INSTALLER = PACKAGES[PACKAGE_FULL]
UPDATE_INFO_FILE = os.path.join(DIST_DIR, UPDATE_INFO_FILE_NAME)
# What each release brings, in every language, keyed by version: the build puts them into
# update.json, and installed copies show them when they offer the release.
RELEASE_NOTES_FILE = os.path.join(BASE_DIR, "release_notes.json")
# Stands where an address goes until RELEASES_URL in core/constants.py is set.
ADDRESS_TO_FILL_IN = "https://REPLACE-WITH-THE-RELEASES-ADDRESS"
# Read-only files the program loads at run time.
DATA_FOLDERS = ("locales", "assets")
# Packages whose DLLs and data files PyInstaller does not find from the imports
# alone: the screen reader bridges, the audio device library, the codecs, and the
# SOCKS library Telethon loads only once a proxy is set.
COLLECTED_PACKAGES = ("accessible_output2", "sounddevice", "av", "python_socks")
# Where Inno Setup puts its compiler, the newer version first.
INNO_SETUP_COMPILERS = tuple(
    os.path.join(folder, "Inno Setup " + version, "ISCC.exe")
    for version in ("7", "6")
    for folder in (
        os.environ.get("ProgramFiles(x86)", ""), os.environ.get("ProgramFiles", ""),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs"),
    )
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


REQUIREMENTS_FILES = (os.path.join(BASE_DIR, "requirements.txt"), os.path.join(BASE_DIR, "requirements-build.txt"))
# The release key: private, kept out of git (.gitignore) and never shipped. Back it up: without it no
# later release can be signed, and the copies installed would not take one.
SIGNING_KEY_FILE = os.path.join(BASE_DIR, "release_signing_key.pem")


# Authenticode, for Windows to name the publisher: a code signing certificate, given as the path of its
# .pfx file (with its password in SIGN_PASSWORD_ENV) or as the SHA-1 thumbprint of one in the Windows
# certificate store, or on a hardware token. Without it the build signs nothing and says so.
SIGN_CERTIFICATE_ENV = "AURAGRAM_SIGN_CERT"
SIGN_PASSWORD_ENV = "AURAGRAM_SIGN_PASSWORD"
# A signature stamped with the time stays valid after the certificate expires.
TIMESTAMP_URL = "http://timestamp.digicert.com"
WINDOWS_KITS = os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Windows Kits", "10", "bin")


def find_signtool():
    """signtool.exe from the newest Windows SDK installed, or from the PATH; None if there is none."""
    import glob
    found = sorted(glob.glob(os.path.join(WINDOWS_KITS, "*", "x64", "signtool.exe")))
    return found[-1] if found else shutil.which("signtool")


def signtool_command(tool, certificate, password, paths):
    command = [tool, "sign", "/fd", "SHA256", "/tr", TIMESTAMP_URL, "/td", "SHA256"]
    if os.path.isfile(certificate):
        command += ["/f", certificate] + (["/p", password] if password else [])
    else:
        command += ["/sha1", certificate.replace(" ", "")]
    return command + list(paths)


def authenticode(paths):
    """Sign programs with the code signing certificate, where one is set up; False if none is."""
    certificate = os.environ.get(SIGN_CERTIFICATE_ENV)
    if not certificate:
        print("NOTE: no code signing certificate (%s), so Windows will call the publisher unknown." % SIGN_CERTIFICATE_ENV)
        return False
    tool = find_signtool()
    if tool is None:
        sys.exit("Build stopped: signing needs signtool.exe, from the Windows SDK.")
    run(signtool_command(tool, certificate, os.environ.get(SIGN_PASSWORD_ENV), paths))
    return True


def load_signing_key(path=SIGNING_KEY_FILE):
    """The private release key; None if this computer has none."""
    try:
        with open(path, "rb") as key_file:
            return signing.rsa.PrivateKey.load_pkcs1(key_file.read())
    except OSError:
        return None


def sign_release_file(path, private_key=None, public_keys=None):
    """Sign update.json where it is, after checking that the copies installed will take the signature.
    Stops the build if they would not: a release they refuse is no release for them."""
    private_key = private_key or load_signing_key()
    public_keys = signing.load_public_keys() if public_keys is None else public_keys
    if not public_keys:
        print("NOTE: the program trusts no release key (%s), so the release file is not signed." % signing.TRUSTED_KEYS_FILE)
        return False
    if private_key is None:
        sys.exit("Build stopped: the program takes only signed releases, and %s is missing." % SIGNING_KEY_FILE)
    with open(path, encoding="utf-8") as info_file:
        info = json.load(info_file)
    signed = signing.sign(info, private_key)
    if not signing.is_signed_by(signed, public_keys):
        sys.exit("Build stopped: %s is not the key the program trusts." % SIGNING_KEY_FILE)
    with open(path, "w", encoding="utf-8") as info_file:
        json.dump(signed, info_file, ensure_ascii=False, indent=4)
        info_file.write("\n")
    print("Signed %s with the release key." % path)
    return True


def make_signing_key():
    """Make the release key once: the private half beside the project, the public half shipped with the program."""
    if os.path.exists(SIGNING_KEY_FILE):
        sys.exit("There is a release key already (%s); a new one would leave the copies installed behind." % SIGNING_KEY_FILE)
    print("Making a %d-bit release key; this takes a minute or so..." % signing.KEY_BITS, flush=True)
    public_key, private_key = signing.make_keys()
    with open(SIGNING_KEY_FILE, "wb") as key_file:
        key_file.write(private_key.save_pkcs1())
    # Added to those trusted, not in their place: a copy installed before still takes what an old key signed.
    with open(signing.TRUSTED_KEYS_FILE, "ab") as keys_file:
        keys_file.write(public_key.save_pkcs1())
    print("Private key: %s  (keep a copy somewhere safe, and never share it)" % SIGNING_KEY_FILE)
    print("Public key added to: %s" % signing.TRUSTED_KEYS_FILE)


def step(title):
    print("\n=== %s ===" % title, flush=True)


def pinned_versions(paths=REQUIREMENTS_FILES):
    """{package name in lower case: version} for every "name==version" line of the requirements files."""
    pins = {}
    for path in paths:
        with open(path, encoding="utf-8") as requirements:
            for line in requirements:
                line = line.split("#", 1)[0].strip()
                if "==" not in line:
                    continue
                name, version = line.split("==", 1)
                # "python-socks[asyncio]": the package is python-socks.
                pins[name.split("[", 1)[0].strip().lower().replace("_", "-")] = version.strip()
    return pins


def version_mismatches(pins, installed):
    """[(package, pinned, installed or None)] for each pinned package installed at another version, or not at all.
    `installed(name)` gives a package's version, raising if it is not installed (importlib.metadata raises
    PackageNotFoundError, an ImportError)."""
    found = []
    for name, version in sorted(pins.items()):
        try:
            have = installed(name)
        except (LookupError, ImportError):
            have = None
        if have != version:
            found.append((name, version, have))
    return found


def check_versions():
    """Stop unless the libraries installed are the ones requirements.txt names: a build made with others
    would ship an update that does not fit the copies already installed."""
    import importlib.metadata
    step("Checking the libraries' versions")
    mismatches = version_mismatches(pinned_versions(), importlib.metadata.version)
    if not mismatches:
        print("Every library is at the version the program is tested with.")
        return
    for name, version, have in mismatches:
        print("  %s: needs %s, has %s" % (name, version, have or "nothing"))
    sys.exit("Build stopped: install the pinned versions (pip install -r requirements-build.txt), or raise the pins on purpose.")


def run(command):
    """Run a command, stopping the build if it fails."""
    result = subprocess.run(command, cwd=BASE_DIR)
    if result.returncode != 0:
        sys.exit("Build stopped: %s failed (exit code %d)." % (os.path.basename(command[0]), result.returncode))


def run_tests():
    """Run every test; what they print is shown and also kept in TESTS_LOG_FILE, so a failure
    that scrolled out of sight can still be read whole."""
    step("Running the tests")
    os.makedirs(WORK_DIR, exist_ok=True)
    command = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."]
    with open(TESTS_LOG_FILE, "w", encoding="utf-8") as log:
        process = subprocess.Popen(command, cwd=BASE_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, encoding="utf-8", errors="replace")
        for line in process.stdout:
            sys.stdout.write(line)
            log.write(line)
        process.wait()
    if process.returncode != 0:
        sys.exit("Build stopped: the tests failed. Everything they printed is in %s" % TESTS_LOG_FILE)


def write_version_info():
    """Describe the program to Windows, so its Properties window shows the name and version."""
    # Windows wants four numbers: 1.1 is 1.1.0.0.
    numbers = (tuple(int(part) for part in APP_VERSION.split(".")) + (0, 0, 0, 0))[:4]
    os.makedirs(WORK_DIR, exist_ok=True)
    with open(VERSION_INFO_FILE, "w", encoding="utf-8") as version_file:
        version_file.write(VERSION_INFO_TEMPLATE.format(
            numbers=numbers, name=APP_NAME, version=APP_VERSION,
            publisher=APP_PUBLISHER, copyright=APP_COPYRIGHT
        ))


def write_bundled_config():
    """Prepare the API id and hash that go inside the program, taken from this project's config.json.

    Only those two values are packed: never the session file, which is a login to
    one person's account. Returns the modules the program must take along for them,
    or None if nothing is packed: no usable config.json, or no private part to pack with.
    """
    api_id, api_hash = read_credentials(CONFIG_FILE)
    if not api_id:
        print("NOTE: no valid config.json in the project, so the built program will ask")
        print("      every user for an API id and hash on first run.")
        return None
    os.makedirs(WORK_DIR, exist_ok=True)
    packed = pack_credentials(api_id, api_hash)
    if packed is None:
        print("NOTE: this copy of the code cannot pack an API id and hash into the program,")
        print("      so the built program will ask every user for their own on first run.")
        return None
    data, modules = packed
    with open(BUNDLED_CONFIG_BUILD_FILE, "wb") as config_file:
        config_file.write(data)
    print("Packing this project's API id and hash into the program.")
    return modules


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
    modules = write_bundled_config()
    if modules is not None:
        command += ["--add-data", BUNDLED_CONFIG_BUILD_FILE + os.pathsep + "."]
        for module in modules:
            command += ["--hidden-import", module]
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
        print("Inno Setup was not found, so no installer was made.")
        print("Install it from https://jrsoftware.org/isinfo.php and run this script again.")
        return False
    # The whole installer, then the small one that only brings an installed copy up to date.
    for extra in ([], ["/DUpdateOnly=1"]):
        run([
            compiler, "/Qp", "/DAppVersion=" + APP_VERSION, "/DAppPublisher=" + APP_PUBLISHER,
            "/DAppCopyright=" + APP_COPYRIGHT, *extra, os.path.join(BASE_DIR, "installer.iss")
        ])
    return True


def release_notes(version=APP_VERSION, path=RELEASE_NOTES_FILE):
    """{language: what this version brings}, from RELEASE_NOTES_FILE; empty where nothing is written."""
    try:
        with open(path, encoding="utf-8") as notes_file:
            written = json.load(notes_file).get(version) or {}
    except (OSError, ValueError):
        written = {}
    return {language: written.get(language, "").strip() for language in LANGUAGES}


def write_update_info():
    """Describe this release for the copies already installed: what to fetch and how to know it came whole.

    Upload the two installers to the release, and put the file where UPDATE_INFO_URL points.
    """
    step("Writing " + UPDATE_INFO_FILE_NAME)
    releases = RELEASES_URL.rstrip("/") or ADDRESS_TO_FILL_IN
    tag = "v" + APP_VERSION
    notes = release_notes()
    info = {
        "version": APP_VERSION,
        "url": "%s/tag/%s" % (releases, tag),
        "notes": notes,
    }
    for kind, path in PACKAGES.items():
        info[kind] = updates.describe_file(path, "%s/download/%s/%s" % (releases, tag, os.path.basename(path)))
    info[PACKAGE_UPDATE]["from"] = UPDATE_BASE_VERSION
    with open(UPDATE_INFO_FILE, "w", encoding="utf-8") as info_file:
        json.dump(info, info_file, ensure_ascii=False, indent=4)
        info_file.write("\n")
    sign_release_file(UPDATE_INFO_FILE)
    missing = [language for language, text in notes.items() if not text]
    if missing:
        print("NOTE: %s has no notes for %s in %s." % (APP_VERSION, ", ".join(missing), RELEASE_NOTES_FILE))
        print("      Write them there and build again, or into the file and: python build.py --sign-update")
    if not RELEASES_URL:
        print("NOTE: RELEASES_URL is not set in core/constants.py, so the addresses in the file")
        print("      are placeholders. Set it, or write the real addresses in by hand.")


def folder_size_mb(path):
    total = sum(
        os.path.getsize(os.path.join(root, name)) for root, _, names in os.walk(path) for name in names
    )
    return total / (1024 * 1024)


def main():
    if "--make-signing-key" in sys.argv:
        make_signing_key()
        return
    if "--sign-update" in sys.argv:
        sign_release_file(UPDATE_INFO_FILE)
        return
    check_versions()
    if "--skip-tests" not in sys.argv:
        run_tests()
    build_program()
    check_program()
    # Before the installers take it in, so the program they install is signed too.
    step("Signing the program")
    authenticode([PROGRAM])
    has_installer = build_installer()
    if has_installer:
        step("Signing the installers")
        authenticode(list(PACKAGES.values()))
        # After the signing: their SHA-256 is that of the signed files.
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

# PyInstaller build spec for the mobcal command (Windows, macOS, Linux).
#
# Run through `tools/build_bundle.py` (on Windows, through `tools/build_exe.ps1`, which cuts PATH
# first), not `pyinstaller` directly: the tool also puts the Fortran binaries, their build.json
# and the examples beside the executable, and runs the self-check on the result.
#
# Onedir, not onefile: a onefile executable extracts itself to a temporary directory on every
# start, and Inno Setup wants a folder to copy. The result is dist/mobcal/, holding the mobcal
# executable and PyInstaller's _internal/; build_bundle.py adds fortran/ and examples/ beside it,
# where mobcal.fortran.binary_dir() and examples_dir() look in a frozen program.
#
# Two executables in the one folder: `mobcal`, the console program (the command line, whose
# `mobcal gui` also opens the window), and `mobcal-gui`, windowed, which opens the window and
# nothing else: on Windows the Start-menu shortcut's target, which must not open a console; on
# macOS the executable of MOBCAL.app, which BUNDLE wraps around the folder. Two Analyses of the
# same package, since each executable freezes its own entry script; COLLECT keeps one copy of
# what they share. The third-party runtime dependencies are cclib, which `mobcal import` loads
# to read an ORCA output, with numpy, scipy and periodictable under it (PyInstaller's own hooks
# cover numpy and scipy; periodictable's tables are collected here because no hook does), and
# PySide6-Essentials, which only mobcal.app imports and PyInstaller's hook collects with the
# Qt plugins QtCore, QtGui and QtWidgets need. On Linux, Qt >= 6.5's xcb platform plugin needs
# libxcb-cursor.so.0, which many desktops lack; the build machine's copy is collected beside
# the plugin. The package's data files are the element tables (each gas's default set and the
# named alternates) and the settings file, which the self-check verifies by SHA-256.

import os
import sys

from PyInstaller.utils.hooks import collect_data_files

ROOT = os.path.dirname(SPECPATH)  # SPECPATH is injected by PyInstaller: packaging/

XCB_CURSOR = "libxcb-cursor.so.0"
_binaries = []
if sys.platform.startswith("linux"):
    _found = [os.path.join(d, XCB_CURSOR) for d in ("/usr/lib/x86_64-linux-gnu",
                                                    "/usr/lib/aarch64-linux-gnu", "/usr/lib64",
                                                    "/usr/lib")
              if os.path.isfile(os.path.join(d, XCB_CURSOR))]
    if not _found:
        raise RuntimeError(f"Refusing to build: no {XCB_CURSOR} on this machine to ship beside "
                           "Qt's xcb plugin (apt-get install libxcb-cursor0), so the window "
                           "would not start on a desktop that lacks it.")
    _binaries.append((_found[0], "."))


def _analysis(script):
    return Analysis(
        [os.path.join(SPECPATH, script)],
        pathex=[os.path.join(ROOT, "src")],
        binaries=_binaries,
        # The element tables, beside mobcal/parameters/__init__ where mobcal.parameters looks,
        # and the 2012 settings file beside mobcal/settings/__init__.
        datas=[(os.path.join(ROOT, "src", "mobcal", "parameters", "*.toml"),
                os.path.join("mobcal", "parameters")),
               (os.path.join(ROOT, "src", "mobcal", "settings", "*.toml"),
                os.path.join("mobcal", "settings"))] + collect_data_files("periodictable"),
        hiddenimports=[],
        hookspath=[],
        hooksconfig={},
        runtime_hooks=[],
        # scipy names pytest in its test helpers, which drags in pytest, pluggy and setuptools,
        # and with setuptools a runtime hook that imports it on every start (0.3 s on
        # Windows). Nothing mobcal runs reaches them; build_bundle.py's import check runs the
        # path that loads scipy. tkinter is not the window's toolkit.
        excludes=["tkinter", "_tkinter", "pytest", "_pytest", "pluggy", "setuptools",
                  "_distutils_hack", "pkg_resources"],
        noarchive=False,
    )


a = _analysis("entrypoint.py")
g = _analysis("gui_entrypoint.py")

# PySide6's wheels carry Qt itself, built for glibc 2.28, and take the desktop's own glib,
# fontconfig, freetype, X11/xcb, xkbcommon, EGL/GL and D-Bus, which every desktop has. PyInstaller
# would otherwise copy the build machine's, which ask for its glibc (2.43 on ubuntu-latest, and
# `mobcal gui` stopped on Debian stable for it). Those stay the host's; libxcb-cursor is the
# exception, shipped because a desktop may lack it. Every other system library the bundle still
# carries is printed, so a build log says what the Linux archive assumes.
if sys.platform.startswith("linux"):
    import re

    _HOST = re.compile(r"^lib(glib-2|gobject-2|gio-2|gthread-2|gmodule-2|EGL|GL|GLX|GLdispatch|"
                       r"OpenGL|fontconfig|freetype|xkbcommon|X11|Xext|Xau|Xdmcp|Xrender|Xi\b|"
                       r"xcb(?!-cursor)|dbus-1|systemd|icu|png16|harfbuzz|graphite2|brotli|"
                       r"expat|pcre2|gcrypt|gpg-error|lz4|cap\b|selinux|mount|blkid)")
    _SYSTEM = ("/lib/", "/lib64/", "/usr/lib/", "/usr/lib64/")

    # Qt plugins the window never loads, which bring the build machine's GTK 3 stack (the gtk3
    # platform theme) and Kerberos (the network plugins), and the libraries only they need:
    # they took the Linux folder to 420 MB, and the GTK stack asks for the build machine's glibc.
    _UNUSED_PLUGIN = re.compile(r"plugins/(platformthemes/libqgtk3|tls/|networkinformation/)")
    _ONLY_THEIRS = re.compile(r"^lib(gtk-3|gdk-3|gdk_pixbuf|atk|atspi|cairo|pango|pixman|"
                              r"epoxy|fribidi|thai|datrie|glycin|lcms2|Xcomposite|Xdamage|"
                              r"Xinerama|Xrandr|Xcursor|XRes|gssapi_krb5|krb5|k5crypto|"
                              r"com_err|keyutils|seccomp)")

    def _host_libs_out(toc):
        return [e for e in toc
                if not (e[1].startswith(_SYSTEM) and (_HOST.match(os.path.basename(e[0]))
                                                      or _ONLY_THEIRS.match(
                                                          os.path.basename(e[0]))))
                and not _UNUSED_PLUGIN.search(e[0].replace("\\", "/"))]

    a.binaries = _host_libs_out(a.binaries)
    g.binaries = _host_libs_out(g.binaries)
    for _dest in sorted({e[0] for e in list(a.binaries) + list(g.binaries)
                         if e[1].startswith(_SYSTEM)}):
        print(f"mobcal.spec: system library kept in the bundle: {_dest}")

if not any(name == "mobcal.selfcheck" for name, *_ in a.pure):
    raise RuntimeError("Refusing to build: mobcal.selfcheck is not in the bundle, so the "
                       "installed program could not check itself. The Analysis did not follow "
                       "cli.py's import of it.")

_pure = {name for name, *_ in a.pure}
_import = {"mobcal.io.structure", "cclib.io.ccio", "cclib.parser.orcaparser",
           "cclib.parser.gaussianparser"}
if not _import <= _pure:
    raise RuntimeError(f"Refusing to build: {sorted(_import - _pure)} are not in the bundle, so "
                       "`mobcal import` could not read an ORCA output or recognize a Gaussian "
                       "one. The Analysis did not follow cli.py's import of mobcal.io.structure "
                       "or its import of cclib.")

# The window's modules are pure Python; Qt's are extension modules, so among the binaries.
_window = {"mobcal.app", "mobcal.app.window"}
_qt = {os.path.splitext(os.path.basename(dest))[0].split(".")[0] for dest, *_ in g.binaries
       if os.path.dirname(dest).replace("\\", "/").endswith("PySide6")}
_missing = sorted(_window - {name for name, *_ in g.pure}) + sorted(
    {"QtCore", "QtGui", "QtWidgets"} - _qt)
if _missing:
    raise RuntimeError(f"Refusing to build: {_missing} are not in the bundle, so `mobcal gui` "
                       "could not open the window.")

_tables = {os.path.basename(dest) for dest, *_ in a.datas
           if dest.endswith(".toml") and dest.startswith("mobcal")}
_want = {"mobcal_He.toml", "mobcal_He_2000.toml", "mobcal_N2.toml", "mobcal_2012.toml"}
if _tables != _want:
    raise RuntimeError(f"Refusing to build: the data files in the bundle are {_tables}, not "
                       f"{_want}; no run could start without the tables, a named set "
                       "missing would be refused, and the settings file is what the window "
                       "reads.")

# --- Provenance guard (Windows) -------------------------------------------------------------
# PyInstaller resolves a collected binary's DLL dependencies through the binary's own directory,
# then sys.path, then PATH. A PATH carrying another Python distribution substitutes its DLLs
# quietly (a sibling project once shipped a build that died on start this way).
# tools/build_exe.ps1 cuts PATH down to the Windows directories and uv's; this refuses to ship
# anything that still gets through. Legitimate sources are the venv, the interpreter it was
# made from, and this repo. Not applied on macOS and Linux, where the interpreter's own system
# libraries are legitimately outside all three.
if sys.platform == "win32":
    def _real(path):
        # realpath through uv's junctioned interpreter directory returns a file with the \\?\
        # prefix and the directory without it.
        p = os.path.realpath(path)
        return os.path.normcase(p[4:] if p.startswith("\\\\?\\") else p)

    allowed = tuple(_real(p).rstrip(os.sep) + os.sep for p in (sys.prefix, sys.base_prefix, ROOT))
    foreign = [e for e in list(a.binaries) + list(a.datas) + list(g.binaries) + list(g.datas)
               if not _real(e[1]).startswith(allowed)]
    if foreign:
        raise RuntimeError(
            "Refusing to build: these files come from outside the venv, its base interpreter "
            "and this repo (a foreign directory on PATH, most likely another Python "
            "distribution):\n" + "\n".join(f"  {dest}  <-  {src}" for dest, src, *_ in foreign))

def _exe(analysis, name, console):
    return EXE(
        PYZ(analysis.pure, analysis.zipped_data),
        analysis.scripts,
        [],
        exclude_binaries=True,
        name=name,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=console,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )


exe = _exe(a, "mobcal", console=True)
exe_gui = _exe(g, "mobcal-gui", console=False)

if sys.platform == "darwin":
    # The .app's executable is the first EXE its COLLECT names. The console program sits beside
    # it in Contents/MacOS, where build_bundle.py also puts fortran/ and examples/.
    coll = COLLECT(exe_gui, exe, a.binaries, a.datas, g.binaries, g.datas, strip=False,
                   upx=False, upx_exclude=[], name="mobcal")
    app = BUNDLE(coll, name="MOBCAL.app", icon=None, bundle_identifier="edu.uw.bushgroup.mobcal",
                 info_plist={"CFBundleName": "MOBCAL", "CFBundleDisplayName": "MOBCAL",
                             "NSHighResolutionCapable": True})
else:
    coll = COLLECT(exe, exe_gui, a.binaries, a.datas, g.binaries, g.datas, strip=False,
                   upx=False, upx_exclude=[], name="mobcal")

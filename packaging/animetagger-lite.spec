# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller onedir definition shared by CPU and CUDA portable builds."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_dynamic_libs


PROJECT_ROOT = Path(SPECPATH).resolve().parent
VARIANT = os.environ.get("ANIMETAGGER_BUILD_VARIANT", "").casefold()
ONEFILE = os.environ.get("ANIMETAGGER_ONEFILE") == "1"
DEBUG_CONSOLE = os.environ.get("ANIMETAGGER_DEBUG_CONSOLE") == "1"
if VARIANT not in {"cpu", "cuda"}:
    raise SystemExit(
        "ANIMETAGGER_BUILD_VARIANT must be exactly 'cpu' or 'cuda'."
    )


def nvidia_runtime_binaries() -> list[tuple[str, str]]:
    spec = importlib.util.find_spec("nvidia")
    if spec is None or not spec.submodule_search_locations:
        raise SystemExit(
            "CUDA build requires the official NVIDIA runtime packages supplied "
            "by onnxruntime-gpu[cuda,cudnn]."
        )
    root = Path(next(iter(spec.submodule_search_locations)))
    directories = (
        (root / "cu13" / "bin" / "x86_64", "nvidia/cu13/bin/x86_64"),
        (root / "cudnn" / "bin", "nvidia/cudnn/bin"),
    )
    binaries: list[tuple[str, str]] = []
    for source, destination in directories:
        dlls = sorted(source.glob("*.dll"))
        if not dlls:
            raise SystemExit(f"No NVIDIA runtime DLLs found in {source}.")
        binaries.extend((str(path), destination) for path in dlls)
    return binaries


def torchvision_extension_binaries() -> list[tuple[str, str]]:
    """Ship torchvision's C extensions (torch.ops.load_library expects them on disk)."""
    spec = importlib.util.find_spec("torchvision")
    if spec is None or not spec.submodule_search_locations:
        return []
    root = Path(next(iter(spec.submodule_search_locations)))
    binaries: list[tuple[str, str]] = []
    for path in sorted(root.glob("*.pyd")) + sorted(root.glob("*.dll")):
        binaries.append((str(path), "torchvision"))
    return binaries


binaries = collect_dynamic_libs("onnxruntime")
binaries += collect_dynamic_libs("pillow_heif")
binaries += torchvision_extension_binaries()
if VARIANT == "cuda":
    binaries += nvidia_runtime_binaries()

excluded = [
    "PySide6.QtNetwork",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuickControls2",
    "PySide6.QtVirtualKeyboard",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtWebEngineWidgets",
    "_pytest",
    "pytest",
    "pytestqt",
    "tensorflow",
]

a = Analysis(
    [str(PROJECT_ROOT / "app" / "portable_entry.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=binaries,
    # User-editable JSON resources and release documents are deliberately
    # staged beside the executables by scripts/build_portable.py. They must
    # not be hidden inside _internal or resolved from the source tree.
    datas=[],
    hiddenimports=["app.batch_cli", "timm", "safetensors.torch"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excluded,
    noarchive=False,
    optimize=1,
)


def keep_release_artifact(entry) -> bool:
    """Remove unused providers/Qt features while retaining required plugins."""

    destination = entry[0].replace("\\", "/").casefold()
    file_name = destination.rsplit("/", 1)[-1]
    if file_name == "icuuc.dll" or (
        file_name.startswith("icudt") and file_name.endswith(".dll")
    ):
        # Qt uses Windows' unversioned ICU interface.  PyInstaller can resolve
        # an unrelated ICU build from the developer PATH (for example
        # Poppler's version-suffixed ICU 78), which then makes QtCore fail with
        # ERROR_PROC_NOT_FOUND on a clean Explorer launch.
        return False
    if destination.endswith("onnxruntime_providers_tensorrt.dll"):
        # TensorRT is not a supported AnimeTagger Lite device mode and its
        # proprietary runtime is intentionally not shipped. CUDA remains the
        # only GPU execution provider offered by this package.
        return False
    if destination.startswith("pyside6/translations/"):
        return destination.endswith(("_zh_cn.qm", "_zh_tw.qm"))
    if destination.startswith(
        (
            "pyside6/plugins/networkinformation/",
            "pyside6/plugins/platforminputcontexts/",
            "pyside6/plugins/tls/",
            "pyside6/qml/",
        )
    ):
        return False
    if destination == "pyside6/plugins/imageformats/qpdf.dll":
        return False
    if "/tests/" in "/" + destination or "/__pycache__/" in "/" + destination:
        return False
    return destination not in {
        "pyside6/qtnetwork.pyd",
        "pyside6/qt6network.dll",
        "pyside6/qt6pdf.dll",
        "pyside6/qt6qml.dll",
        "pyside6/qt6qmlmeta.dll",
        "pyside6/qt6qmlmodels.dll",
        "pyside6/qt6qmlworkerscript.dll",
        "pyside6/qt6quick.dll",
        "pyside6/qt6virtualkeyboard.dll",
    }


a.binaries = [entry for entry in a.binaries if keep_release_artifact(entry)]
a.datas = [entry for entry in a.datas if keep_release_artifact(entry)]
pyz = PYZ(a.pure)

if ONEFILE:
    gui = EXE(
        pyz, a.scripts, a.binaries, a.datas, [],
        name="AnimeTaggerLite",
        debug=False, strip=False, upx=False,
        console=DEBUG_CONSOLE,
        disable_windowed_traceback=False,
    )
else:
    gui = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="AnimeTaggerLite",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=DEBUG_CONSOLE,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        contents_directory="_internal",
    )

    cli = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="AnimeTaggerLiteCLI",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=True,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        contents_directory="_internal",
    )

    coll = COLLECT(
        gui,
        cli,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        upx_exclude=[],
        name="AnimeTaggerLite",
    )

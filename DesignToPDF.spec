# -*- mode: python ; coding: utf-8 -*-

import os

from PyInstaller.utils.hooks import collect_data_files

ICON_FILE = os.path.abspath("assets/app.ico")
ICON_PNG = os.path.abspath("assets/app_icon.png")

try:
    import PySide2  # noqa: F401

    QT_HIDDEN = [
        "PySide2.QtCore",
        "PySide2.QtGui",
        "PySide2.QtWidgets",
        "PySide2.QtNetwork",
    ]
    QT_EXCLUDES = [
        "PySide6",
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
    ]
except ImportError:
    QT_HIDDEN = [
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
    ]
    QT_EXCLUDES = [
        "PySide6.QtWebEngine",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.Qt3DAnimation",
        "PySide6.Qt3DCore",
        "PySide6.Qt3DExtras",
        "PySide6.Qt3DInput",
        "PySide6.Qt3DLogic",
        "PySide6.Qt3DRender",
        "PySide6.QtBluetooth",
        "PySide6.QtCharts",
        "PySide6.QtDataVisualization",
        "PySide6.QtMultimedia",
        "PySide6.QtMultimediaWidgets",
        "PySide6.QtPositioning",
        "PySide6.QtQuick",
        "PySide6.QtQuick3D",
        "PySide6.QtQuickWidgets",
        "PySide6.QtRemoteObjects",
        "PySide6.QtSensors",
        "PySide6.QtSerialPort",
        "PySide6.QtSql",
        "PySide6.QtTest",
        "PySide6.QtTextToSpeech",
        "PySide6.QtWebChannel",
        "PySide6.QtWebSockets",
        "PySide6.QtNetworkAuth",
        "PySide6.QtNfc",
        "PySide6.QtPdf",
        "PySide6.QtPdfWidgets",
        "PySide6.QtLocation",
        "PySide6.QtQml",
        "PySide6.QtDesigner",
        "PySide6.QtHelp",
        "PySide6.QtHttpServer",
        "PySide6.QtOpenGL",
        "PySide6.QtOpenGLWidgets",
        "PySide6.QtSpatialAudio",
        "PySide6.QtSvg",
        "PySide6.QtSvgWidgets",
    ]

hiddenimports = [
    "brand",
    "convert",
    "export_kind",
    "source_scan",
    "qt_compat",
    "pymupdf",
    "PIL",
    "PIL.Image",
    "PIL.PdfImagePlugin",
    "PIL.JpegImagePlugin",
    "PIL.PngImagePlugin",
    "PIL.BmpImagePlugin",
    "PIL.GifImagePlugin",
    "PIL.TiffImagePlugin",
    "PIL.WebPImagePlugin",
    "PIL.TgaImagePlugin",
    "reportlab",
    "reportlab.graphics",
    "reportlab.graphics.renderPDF",
    "svglib",
    "svglib.svglib",
] + QT_HIDDEN

excludes = [
    "tkinter",
    "matplotlib",
    "numpy",
    "pkg_resources",
    "setuptools",
] + QT_EXCLUDES

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=[],
    datas=collect_data_files("reportlab") + collect_data_files("svglib") + [
        (ICON_FILE, "assets"),
        (ICON_PNG, "assets"),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

# setuptools 70 拆掉了 pkg_resources.extern，运行时钩子会直接崩。本程序不用它。
a.scripts = [s for s in a.scripts if "pyi_rth_pkgres" not in s[0]]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="DesignToPDF",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    version="file_version_info.txt",
    icon=ICON_FILE,
)

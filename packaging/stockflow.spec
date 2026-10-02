# -*- mode: python ; coding: utf-8 -*-
"""Receita de empacotamento do StockFlow para PyInstaller.

Nao executar este arquivo direto. Use:

    uv run python scripts/build_desktop.py

A mesma receita atende Linux e Windows; as diferencas entre os dois
ficam isoladas nas constantes do topo.
"""

import platform
import sys
import tomllib
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files


# ======================================================
# CAMINHOS E NOME DO EXECUTAVEL
# ======================================================

# SPECPATH e injetado pelo PyInstaller: e a pasta deste .spec
PROJECT_ROOT = Path(SPECPATH).parent

ENTRY_POINT = PROJECT_ROOT / "app" / "__main__.py"

with open(PROJECT_ROOT / "pyproject.toml", "rb") as arquivo:
    VERSION = tomllib.load(arquivo)["project"]["version"]

SISTEMA = {
    "linux": "linux",
    "win32": "windows",
    "darwin": "macos",
}.get(sys.platform, sys.platform)

ARQUITETURA = {
    "x86_64": "x64",
    "AMD64": "x64",
    "aarch64": "arm64",
    "arm64": "arm64",
}.get(platform.machine(), platform.machine().lower())

EXECUTAVEL = f"StockFlow-{VERSION}-{SISTEMA}-{ARQUITETURA}"


# ======================================================
# DADOS EMBUTIDOS
# ======================================================

# O qtawesome guarda as fontes .ttf dentro do proprio pacote e as
# carrega em tempo de execucao. O PyInstaller nao descobre isso
# sozinho: sem esta linha o app abre com a interface inteira sem
# icone nenhum (sidebar, estoque, novo produto, coming soon).
DATAS = collect_data_files("qtawesome")


# ======================================================
# MODULOS DESCARTADOS
# ======================================================

# O StockFlow usa apenas QtWidgets, QtGui e QtCore. Sem estes
# excludes o bundle passa de 300 MB por arrastar o WebEngine, o
# Qt3D, o QML e o resto do Qt que o projeto nunca importa.
EXCLUDES = [
    "PySide6.Qt3DAnimation",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DExtras",
    "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic",
    "PySide6.Qt3DRender",
    "PySide6.QtBluetooth",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtDesigner",
    "PySide6.QtGraphs",
    "PySide6.QtHelp",
    "PySide6.QtHttpServer",
    "PySide6.QtLocation",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtNfc",
    "PySide6.QtNetworkAuth",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtPositioning",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuick3D",
    "PySide6.QtQuickControls2",
    "PySide6.QtQuickWidgets",
    "PySide6.QtRemoteObjects",
    "PySide6.QtScxml",
    "PySide6.QtSensors",
    "PySide6.QtSerialBus",
    "PySide6.QtSerialPort",
    "PySide6.QtSpatialAudio",
    "PySide6.QtSql",
    "PySide6.QtStateMachine",
    "PySide6.QtTest",
    "PySide6.QtTextToSpeech",
    "PySide6.QtVirtualKeyboard",
    "PySide6.QtWebChannel",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebSockets",
    "tkinter",
]


# ======================================================
# MONTAGEM
# ======================================================

a = Analysis(
    [str(ENTRY_POINT)],
    pathex=[str(PROJECT_ROOT / "src")],
    binaries=[],
    datas=DATAS,
    hiddenimports=["qtawesome"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=0,
)

# ======================================================
# PODA DO TOC
# ======================================================

# O plugin de teclado virtual do Qt nao e usado pelo StockFlow, mas
# entra como dependencia do hook do PySide6 e arrasta a stack inteira
# de QML/Quick junto (~54 MB de bibliotecas). Como ele nao chega por
# `import`, a lista EXCLUDES acima nao o alcanca: a unica forma de
# tirar e filtrar o TOC depois da Analysis.
PODAR = (
    "libqtvirtualkeyboardplugin",
    "libQt6Qml",
    "libQt6Quick",
)


def podar(toc):
    """Remove do TOC as entradas que casam com PODAR."""

    return [
        entrada
        for entrada in toc
        if not any(termo in entrada[0] for termo in PODAR)
    ]


a.binaries = podar(a.binaries)
a.datas = podar(a.datas)


pyz = PYZ(a.pure)

# Arquivo unico: binarios e dados entram dentro do proprio executavel,
# sem COLLECT. Custo: o primeiro frame demora alguns segundos porque o
# bundle e descompactado numa pasta temporaria a cada execucao.
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=EXECUTAVEL,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    # Sem console: no Windows evita o terminal preto atras da janela.
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

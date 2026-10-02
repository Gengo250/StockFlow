"""Configuração compartilhada dos testes.

Força o backend offscreen do Qt para que a suíte rode em CI/headless e
garante que ``src/`` esteja no ``sys.path`` sem exigir instalação do pacote.
"""

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.fixture(scope="session")
def project_root() -> Path:
    return ROOT


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def signal_spy():
    """Coletor simples de emissões de sinal (evita dependência de pytest-qt)."""

    def _spy(signal):
        received = []
        signal.connect(lambda *args: received.append(args))
        return received

    return _spy

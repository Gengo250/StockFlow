"""Configuração comum dos testes.

Os testes de UI rodam com a plataforma Qt "offscreen", então não é
necessário um servidor gráfico para executá-los.
"""

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def estoque_page(qapp):
    from stockflow.presentation.pages.estoque import EstoquePage

    return EstoquePage()


@pytest.fixture
def vendas_page(qapp):
    from stockflow.presentation.pages.vendas import VendasPage

    return VendasPage()

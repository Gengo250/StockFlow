"""Resumo, exportação e preferências sobre os dados da sessão atual."""

import csv
from decimal import Decimal

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFormLayout, QLabel, QMessageBox,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from stockflow.presentation.widgets.sidebar import DEFAULT_KEY


def preference_prefix(session):
    return f"users/{getattr(session, 'company_id', None) or 'demo'}/{getattr(session, 'user_id', None) or 'guest'}"


class DashboardPage(QWidget):
    def __init__(self, products, sales, clients):
        super().__init__()
        self.products, self.sales, self.clients = products, sales, clients
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 24)
        layout.addWidget(QLabel("Visão geral"))
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setStyleSheet("font-size: 22px; padding: 24px;")
        layout.addWidget(self.summary)
        self.refresh_button = QPushButton("Atualizar resumo")
        self.refresh_button.clicked.connect(self.refresh)
        layout.addWidget(self.refresh_button)
        layout.addStretch()

    def refresh(self):
        try:
            products = self.products.list_all()
            sales = self.sales.list_all()
            clients = self.clients.list_all()
            amount = sum((Decimal(r["total"]) for r in sales), Decimal(0))
            self.summary.setText(
                f"{sum(p.active for p in products)} produtos ativos\n"
                f"{sum(int(p.stock) for p in products)} unidades em estoque\n"
                f"{len(self.products.list_alerts())} produtos no limite mínimo\n"
                f"{sum(c.active for c in clients)} clientes ativos\n"
                f"{len(sales)} vendas registradas · R$ {amount:,.2f}"
            )
        except Exception as error:
            self.summary.setText(f"Não foi possível atualizar o resumo: {error}")


class ReportsPage(QWidget):
    def __init__(self, products, sales):
        super().__init__()
        self.products, self.sales = products, sales
        self.rows = []
        self.headers = []
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Relatórios"))
        self.kind = QComboBox()
        self.kind.addItems(["Estoque", "Vendas"])
        layout.addWidget(self.kind)
        self.table = QTableWidget()
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.table)
        self.error = QLabel()
        layout.addWidget(self.error)
        refresh = QPushButton("Atualizar relatório")
        refresh.clicked.connect(self.refresh)
        layout.addWidget(refresh)
        self.export_button = QPushButton("Exportar CSV")
        self.export_button.clicked.connect(self._choose_export)
        layout.addWidget(self.export_button)
        self.kind.currentIndexChanged.connect(self.refresh)

    def refresh(self):
        try:
            if self.kind.currentIndex() == 0:
                self.headers = ["Código", "Produto", "Categoria", "Saldo", "Mínimo", "Ativo"]
                self.rows = [(p.code, p.name, p.category, p.stock,
                              "" if p.minimum_stock is None else p.minimum_stock, "Sim" if p.active else "Não")
                             for p in self.products.list_all()]
            else:
                self.headers = ["Venda", "Cliente", "Produto", "Valor", "Data"]
                self.rows = [(s["id"], s["cliente"], s["produto"], s["total"], s["data"])
                             for s in self.sales.list_all()]
            self.table.setColumnCount(len(self.headers))
            self.table.setHorizontalHeaderLabels(self.headers)
            self.table.setRowCount(len(self.rows))
            for i, row in enumerate(self.rows):
                for j, value in enumerate(row):
                    self.table.setItem(i, j, QTableWidgetItem(str(value)))
            self.error.clear()
            self.export_button.setEnabled(True)
        except Exception as error:
            self.export_button.setEnabled(False)
            self.error.setText(f"Não foi possível atualizar: {error}")

    def export_csv(self, path):
        # Prevent spreadsheet formulas in user-controlled names/codes.
        def safe(value):
            text = str(value)
            return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) else text
        with open(path, "w", encoding="utf-8-sig", newline="") as output:
            writer = csv.writer(output, delimiter=";")
            writer.writerow(self.headers)
            writer.writerows([safe(v) for v in row] for row in self.rows)

    def _choose_export(self):
        path, _ = QFileDialog.getSaveFileName(self, "Exportar relatório", "relatorio.csv", "CSV (*.csv)")
        if path:
            try:
                self.export_csv(path)
                self.error.setText("Relatório exportado.")
            except OSError as error:
                self.error.setText(f"Não foi possível exportar: {error}")


class SettingsPage(QWidget):
    def __init__(self, session, settings=None):
        super().__init__()
        self.settings = settings or QSettings("StockFlow", "StockFlow")
        self.prefix = preference_prefix(session)
        layout = QFormLayout(self)
        layout.addRow(QLabel("Configurações deste dispositivo"))
        layout.addRow("Conta", QLabel(getattr(session, "email", "") or "Sem sessão"))
        self.start_page = QComboBox()
        for label, key in [("Dashboard", "dashboard"), ("Estoque", "estoque"), ("Produtos", "produtos"), ("Vendas", "vendas")]:
            self.start_page.addItem(label, key)
        # O padrão acompanha o item que a sidebar já nasce marcando como
        # ativo (DEFAULT_KEY). Divergir aqui abria a janela numa tela com o
        # menu apontando para outra.
        key = self.settings.value(self.prefix + "/start_page", DEFAULT_KEY)
        self.start_page.setCurrentIndex(max(0, self.start_page.findData(key)))
        layout.addRow("Tela inicial", self.start_page)
        self.notifications = QCheckBox("Mostrar alertas de estoque")
        self.notifications.setChecked(self.settings.value(self.prefix + "/notifications", True, type=bool))
        layout.addRow(self.notifications)
        save = QPushButton("Salvar preferências")
        save.clicked.connect(self.save)
        layout.addRow(save)
        self.feedback = QLabel()
        layout.addRow(self.feedback)

    def save(self):
        self.settings.setValue(self.prefix + "/start_page", self.start_page.currentData())
        self.settings.setValue(self.prefix + "/notifications", self.notifications.isChecked())
        self.settings.sync()
        self.feedback.setText("Preferências salvas neste dispositivo.")

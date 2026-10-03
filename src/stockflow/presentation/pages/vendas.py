import qtawesome as qta
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from stockflow.presentation.demo_data import base_de_clientes


class VendasPage(QWidget):
    """Página provisória para simulação de vendas e associação de clientes."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("vendasPage")
        self.setStyleSheet("""
            QWidget#vendasPage { background-color: #F0F5FF; }
            QLabel { background-color: transparent; }
            QFrame#card {
                background-color: #FFFFFF;
                border: 1px solid #DBEAFE;
                border-radius: 16px;
            }
            QLineEdit, QComboBox {
                background-color: white;
                color: #0F172A;
                border: 1px solid #BFDBFE;
                border-radius: 10px;
                padding: 8px 12px;
                font-size: 13px;
            }
            QPushButton#primaryButton {
                background-color: #2563EB;
                color: white;
                border: none;
                border-radius: 10px;
                padding: 10px 18px;
                font-weight: 600;
            }
            QPushButton#primaryButton:hover { background-color: #1D4ED8; }
            QTableWidget { background-color: #FFFFFF; border: none; }
            QHeaderView::section {
                background-color: #F8FBFF;
                color: #64748B;
                border: none;
                border-bottom: 1px solid #DBEAFE;
                padding: 10px;
                font-size: 12px;
                font-weight: 600;
            }
        """)

        # Base de clientes para simulação [ID, Nome, Status].
        # Vem de demo_data, a mesma fonte da tabela de Usuários: enquanto as
        # duas telas mantinham listas próprias, usuário ativo lá podia não
        # existir aqui e a associação falhava sem explicação.
        self.clientes = base_de_clientes()

        # Vendas históricas (preservam o nome do cliente associado no momento da venda)
        self.historico_vendas = [
            {"id": "VND-1001", "cliente": "Patrícia Lima", "valor": "R$ 450,00", "data": "10/08/2026"},
            {"id": "VND-1002", "cliente": "Ana Ferreira", "valor": "R$ 1.290,00", "data": "28/09/2026"},
        ]

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(18)

        # Cabeçalho
        title = QLabel("Registro e Seleção de Vendas")
        title.setStyleSheet("color: #0F172A; font-size: 26px; font-weight: 700;")
        layout.addWidget(title)

        # Card de Nova Venda
        form_card = QFrame()
        form_card.setObjectName("card")
        form_layout = QVBoxLayout(form_card)
        form_layout.setContentsMargins(20, 20, 20, 20)
        form_layout.setSpacing(12)

        form_title = QLabel("Nova Venda")
        form_title.setStyleSheet("color: #1E3A8A; font-size: 16px; font-weight: 600;")
        form_layout.addWidget(form_title)

        row = QHBoxLayout()
        row.setSpacing(12)

        # Combo para seleção de cliente
        self.cliente_combo = QComboBox()
        self.cliente_combo.setFixedHeight(42)
        self.recarregar_clientes_disponiveis()
        self.cliente_combo.currentIndexChanged.connect(self._ao_selecionar_cliente)

        # Label de alerta para clientes inativos
        self.warning_label = QLabel("")
        self.warning_label.setStyleSheet("color: #EF4444; font-size: 12px; font-weight: 500;")

        self.val_input = QLineEdit()
        self.val_input.setPlaceholderText("Valor (R$)")
        self.val_input.setFixedHeight(42)

        btn_salvar = QPushButton(" Finalizar Venda")
        btn_salvar.setObjectName("primaryButton")
        btn_salvar.setFixedHeight(42)
        btn_salvar.setIcon(qta.icon("fa5s.check", color="white"))
        btn_salvar.clicked.connect(self._registrar_venda)

        row.addWidget(self.cliente_combo, 2)
        row.addWidget(self.val_input, 1)
        row.addWidget(btn_salvar, 1)
        form_layout.addLayout(row)
        form_layout.addWidget(self.warning_label)

        layout.addWidget(form_card)

        # Tabela de Histórico de Vendas
        hist_title = QLabel("Histórico de Vendas Realizadas")
        hist_title.setStyleSheet("color: #0F172A; font-size: 18px; font-weight: 600;")
        layout.addWidget(hist_title)

        table_card = QFrame()
        table_card.setObjectName("card")
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(0, 0, 0, 0)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["ID Venda", "Cliente Associado", "Valor Total", "Data"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setShowGrid(False)
        self.table.verticalHeader().hide()

        table_layout.addWidget(self.table)
        layout.addWidget(table_card, 1)

        self.atualizar_tabela_historico()

    def recarregar_clientes_disponiveis(self):
        """Preenche o combo apenas com clientes ativos para novas associações."""
        self.cliente_combo.clear()
        self.cliente_combo.addItem("Selecione um cliente...", None)
        
        for cli in self.clientes:
            # Clientes inativos não aparecem na seleção de nova venda
            if cli["status"] == "Ativo":
                self.cliente_combo.addItem(f"{cli['nome']} ({cli['id']})", cli)

    def selecionar_cliente_externo(self, cliente_nome):
        """Permite que a tela de clientes peça para associar um cliente específico."""
        for i in range(self.cliente_combo.count()):
            data = self.cliente_combo.itemData(i)
            if data and data.get("nome") == cliente_nome:
                self.cliente_combo.setCurrentIndex(i)
                # setCurrentIndex não emite sinal quando o índice já era o
                # atual, então o aviso anterior precisa ser limpo aqui.
                self.warning_label.setText("")
                return True

        # Sair do combo tem duas causas distintas: o cliente existe mas não
        # está ativo, ou não existe na base. Relatar sempre "inativo" escondia
        # divergências entre a base de Vendas e a tabela de Usuários.
        cliente = next(
            (c for c in self.clientes if c["nome"] == cliente_nome), None
        )
        if cliente is None:
            self.warning_label.setText(
                f"O cliente '{cliente_nome}' não existe na base de vendas."
            )
        else:
            self.warning_label.setText(
                f"O cliente '{cliente_nome}' está {cliente['status'].lower()} "
                "e não pode ser selecionado."
            )
        return False

    def _ao_selecionar_cliente(self, index):
        self.warning_label.setText("")

    def _registrar_venda(self):
        data = self.cliente_combo.currentData()
        valor = self.val_input.text().strip()

        if not data:
            self.warning_label.setText("Selecione um cliente ativo válido.")
            return

        if not valor:
            self.warning_label.setText("Informe o valor da venda.")
            return

        # Persiste o vínculo gravando o nome do cliente no histórico da venda
        nova_venda = {
            "id": f"VND-100{len(self.historico_vendas) + 1}",
            "cliente": data["nome"],
            "valor": f"R$ {valor}",
            "data": "Hoje",
        }
        self.historico_vendas.insert(0, nova_venda)
        self.val_input.clear()
        self.cliente_combo.setCurrentIndex(0)
        self.warning_label.setText("")
        self.atualizar_tabela_historico()

    def atualizar_tabela_historico(self):
        self.table.setRowCount(len(self.historico_vendas))
        for row, venda in enumerate(self.historico_vendas):
            self.table.setItem(row, 0, QTableWidgetItem(venda["id"]))
            self.table.setItem(row, 1, QTableWidgetItem(venda["cliente"]))
            self.table.setItem(row, 2, QTableWidgetItem(venda["valor"]))
            self.table.setItem(row, 3, QTableWidgetItem(venda["data"]))
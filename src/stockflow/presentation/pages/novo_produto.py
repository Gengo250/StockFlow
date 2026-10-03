import qtawesome as qta

from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from stockflow.application.dto.product_input import ProductInput
from stockflow.presentation.widgets.product_form import (
    BasicInfoCard,
    BeforeRegisterCard,
    PriceTaxCard,
    ProductImageCard,
    ProductStatusCard,
    StockControlCard,
)


def formatar_moeda(valor) -> str:
    """Formata no mesmo padrão de `demo_products`: "R$ 2.499,90".

    O catálogo guarda preço como texto já formatado. Gravar "2499.9" aqui
    faria a ficha do produto mostrar um valor com cara de bug ao lado dos
    demais, e a tela de estoque ordenar por string errada.
    """
    bruto = f"{float(valor):,.2f}"
    return "R$ " + bruto.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def valor_de_moeda(texto) -> float:
    """Inverte `formatar_moeda`: "R$ 2.499,90" vira 2499.9.

    Necessário para reabrir um produto gravado: o catálogo guarda o preço já
    formatado e o campo da tela é um `QDoubleSpinBox`, que só aceita número.
    Texto irreconhecível vira 0.0 em vez de explodir — o formulário é o único
    lugar onde o usuário consegue corrigir o valor.
    """
    if texto is None:
        return 0.0
    limpo = str(texto).replace("R$", "").strip().replace(".", "").replace(",", ".")
    try:
        return float(limpo or 0)
    except ValueError:
        return 0.0


def _para_inteiro(texto) -> int:
    """Estoque do catálogo (texto) para o inteiro que o `QSpinBox` aceita."""
    try:
        return int(str(texto).strip() or 0)
    except ValueError:
        return 0


class NovoProdutoPage(QWidget):
    def __init__(self, edit_mode=False):
        super().__init__()
        self.edit_mode = edit_mode
        self.setObjectName("novoProdutoPage")
        self.setStyleSheet("""
            QWidget#novoProdutoPage { background-color: #F0F5FF; }
            QWidget#novoProdutoPage QLabel { background-color: transparent; }
        """)

        page_layout = QVBoxLayout(self)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea { background-color: #F0F5FF; border: none; }
            QScrollBar:vertical { background: transparent; width: 8px; margin: 4px 2px; }
            QScrollBar::handle:vertical {
                background: #CBD5E1;
                border-radius: 4px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover { background: #94A3B8; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        """)

        content = QWidget()
        content.setObjectName("novoProdutoContent")
        content.setMaximumWidth(1600)
        content.setStyleSheet("""
            QWidget#novoProdutoContent { background-color: #F0F5FF; }
            QWidget#novoProdutoContent QLabel { background-color: transparent; }
        """)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(26, 24, 26, 36)
        content_layout.setSpacing(24)
        content_layout.addWidget(self._create_header())
        content_layout.addLayout(self._create_columns())

        scroll_container = QWidget()
        scroll_container.setObjectName("novoProdutoScrollContainer")
        scroll_container.setStyleSheet("""
            QWidget#novoProdutoScrollContainer { background-color: #F0F5FF; }
        """)
        scroll_layout = QHBoxLayout(scroll_container)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.addStretch()
        scroll_layout.addWidget(content)
        scroll_layout.addStretch()
        scroll.setWidget(scroll_container)
        page_layout.addWidget(scroll)

    def _create_columns(self):
        columns = QHBoxLayout()
        columns.setSpacing(22)
        columns.setContentsMargins(0, 0, 0, 0)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(20)
        self.basic_info_card = BasicInfoCard()
        self.price_tax_card = PriceTaxCard()
        self.stock_control_card = StockControlCard()
        left_layout.addWidget(self.basic_info_card)
        left_layout.addWidget(self.price_tax_card)
        left_layout.addWidget(self.stock_control_card)
        left_layout.addStretch()

        right = QWidget()
        right.setMaximumWidth(430)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(20)
        self.image_card = ProductImageCard()
        self.status_card = ProductStatusCard()
        self.before_register_card = BeforeRegisterCard()
        right_layout.addWidget(self.image_card)
        right_layout.addWidget(self.status_card)
        right_layout.addWidget(self.before_register_card)
        right_layout.addStretch()

        columns.addWidget(left, 7)
        columns.addWidget(right, 3)
        self._expose_form_fields()
        return columns

    def _expose_form_fields(self):
        groups = (
            (self.basic_info_card, (
                "name_input", "code_input", "category_input", "description_input", "description_counter",
            )),
            (self.price_tax_card, (
                "cost_price_input", "sale_price_input", "unit_input", "ncm_input", "ean_input",
            )),
            (self.stock_control_card, (
                "initial_stock_input", "minimum_stock_input", "location_input", "supplier_input", "low_stock_alert",
            )),
            (self.status_card, ("product_status_toggle", "status_dot", "status_label")),
        )
        for widget, names in groups:
            for name in names:
                setattr(self, name, getattr(widget, name))

    def _create_header(self):
        header = QWidget()
        layout = QHBoxLayout(header)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)
        self.back_button = QPushButton("Produtos")
        self.back_button.setIcon(qta.icon("fa5s.chevron-left", color="#64748B"))
        self.back_button.setIconSize(QSize(10, 10))
        self.back_button.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #64748B;
                border: none;
                text-align: left;
                padding: 0px;
                font-size: 13px;
            }
            QPushButton:hover { color: #2563EB; }
        """)
        title = QLabel("Editar produto" if self.edit_mode else "Cadastrar novo produto")
        title.setStyleSheet("""
            background-color: transparent;
            color: #0F172A;
            font-size: 28px;
            font-weight: 700;
        """)
        subtitle = QLabel(
            "Atualize as informações comerciais e de estoque do item."
            if self.edit_mode
            else "Adicione as informações comerciais e de estoque do item."
        )
        subtitle.setStyleSheet("background-color: transparent; color: #64748B; font-size: 14px;")
        self.permission_warning = QLabel(
            "Seu perfil não tem permissão para cadastrar ou editar produtos. "
            "Fale com um administrador."
        )
        self.permission_warning.setWordWrap(True)
        self.permission_warning.setObjectName("permissionWarning")
        self.permission_warning.setStyleSheet("""
            QLabel#permissionWarning {
                background-color: #FEF2F2;
                color: #B91C1C;
                border: 1px solid #FECACA;
                border-radius: 10px;
                padding: 10px 12px;
                font-size: 13px;
                font-weight: 600;
            }
        """)
        self.permission_warning.hide()

        left_layout.addWidget(self.back_button, alignment=Qt.AlignLeft)
        left_layout.addSpacing(6)
        left_layout.addWidget(title)
        left_layout.addWidget(subtitle)
        left_layout.addWidget(self.permission_warning)

        actions = QWidget()
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(10)
        self.cancel_button = self._action_button("Cancelar", """
            QPushButton {
                background-color: #FFFFFF;
                color: #475569;
                border: 1px solid #DBEAFE;
                border-radius: 10px;
                padding: 0px 16px;
                font-size: 14px;
            }
            QPushButton:hover { background-color: #F8FAFC; }
        """)
        # ATENÇÃO: "Salvar rascunho" ainda não tem handler — nenhum clique
        # grava coisa alguma hoje. `apply_permission` já o desabilita junto
        # com o botão de salvar para que ele não prometa uma ação que o papel
        # não tem. Quem for conectar um handler PRECISA passar pelo
        # `ProductService`: ligar o botão direto ao repositório devolveria ao
        # vendedor exatamente a escrita que a US01 fecha.
        self.draft_button = self._action_button("Salvar rascunho", """
            QPushButton {
                background-color: transparent;
                color: #1D4ED8;
                border: none;
                padding: 0px 14px;
                font-size: 14px;
                font-weight: 500;
            }
            QPushButton:hover { color: #1E40AF; }
        """)
        self.draft_button.setVisible(not self.edit_mode)
        self.save_button = self._action_button(
            "Salvar alterações" if self.edit_mode else "Cadastrar produto",
            """
            QPushButton {
                background-color: #2563EB;
                color: white;
                border: none;
                border-radius: 10px;
                padding: 0px 18px;
                font-size: 14px;
                font-weight: 600;
            }
            QPushButton:hover { background-color: #1D4ED8; }
        """,
        )
        self.save_button.setIcon(qta.icon("fa5s.check", color="white"))
        self.save_button.setIconSize(QSize(13, 13))
        actions_layout.addWidget(self.cancel_button)
        actions_layout.addWidget(self.draft_button)
        actions_layout.addWidget(self.save_button)
        layout.addWidget(left, 1)
        layout.addWidget(actions, 0, Qt.AlignTop)
        return header

    @staticmethod
    def _action_button(text, style):
        button = QPushButton(text)
        button.setFixedHeight(40)
        button.setStyleSheet(style)
        return button

    def apply_permission(self, pode_escrever: bool):
        """Controles visuais do papel atual.

        É só a primeira camada: a recusa que vale é a do `ProductService`.
        Esconder o botão sem checar na gravação deixaria qualquer caminho
        alternativo (atalho, script, bug de estado) escrever no catálogo.
        """
        self.save_button.setEnabled(pode_escrever)
        self.draft_button.setEnabled(pode_escrever)
        self.permission_warning.setVisible(not pode_escrever)

    def collect_input(self) -> ProductInput:
        """Lê os widgets e devolve o DTO que o serviço espera."""
        return ProductInput(
            code=self.code_input.text().strip(),
            name=self.name_input.text().strip(),
            category=self.category_input.currentText(),
            unit=self.unit_input.currentText(),
            sale_price=formatar_moeda(self.sale_price_input.value()),
            cost=formatar_moeda(self.cost_price_input.value()),
            stock=str(self.initial_stock_input.value()),
            active=self.product_status_toggle.isChecked(),
        )

    def clear_form(self):
        """Devolve o formulário ao estado de cadastro em branco.

        A página é um widget único reaproveitado a cada abertura. Sem esta
        limpeza, o que sobrou de uma tentativa anterior — inclusive de uma que
        falhou — reaparece na próxima e é gravado como dado do produto novo.
        """
        self.code_input.clear()
        self.name_input.clear()
        self.category_input.setCurrentIndex(0)
        self.description_input.clear()
        self.cost_price_input.setValue(0)
        self.sale_price_input.setValue(0)
        self.unit_input.setCurrentIndex(0)
        self.ncm_input.clear()
        self.ean_input.clear()
        self.initial_stock_input.setValue(0)
        self.minimum_stock_input.setValue(0)
        self.location_input.clear()
        self.supplier_input.setCurrentIndex(0)
        self.low_stock_alert.setChecked(True)
        self.product_status_toggle.setChecked(True)

    def set_catalog_options(self, categories, units):
        """Mostra apenas categorias e unidades ativas para novos produtos."""
        self.category_input.clear()
        self.category_input.addItem("Selecione uma categoria")
        self.category_input.addItems(categories)

        self.unit_input.clear()
        self.unit_input.addItems(units)

    def set_code(self, code: str):
        """Preenche o SKU sugerido.

        O campo é somente leitura e marcado como "Automático" na tela, então
        este é o único caminho que o usuário tem para obter um código: sem a
        chamada, o cadastro vai ao serviço com o código de outro produto.
        """
        self.code_input.setText(code)

    @staticmethod
    def _selecionar(combo, texto):
        """Seleciona o valor no combo, acrescentando-o se ainda não existir.

        Categorias e unidades de produtos antigos podem não estar na lista
        fixa da tela; sem acrescentar, o combo cairia no primeiro item e a
        edição trocaria o valor do produto sem ninguém pedir.
        """
        if not texto:
            return
        if combo.findText(texto) < 0:
            combo.addItem(texto)
        combo.setCurrentText(texto)

    def load_product(self, product):
        """Carrega na tela o produto que vai ser editado.

        Aceita o `Product` completo do catálogo e, por compatibilidade, a
        tupla de 6 campos da tabela de Estoque (código, nome, categoria,
        estoque, preço de venda, status de estoque).

        Prefira SEMPRE o `Product`: a tupla não carrega custo, unidade nem o
        sinalizador de ativo, e `collect_input` lê todos os campos da tela na
        hora de salvar. Carregar pela tupla grava "R$ 0,00" no custo e
        devolve a unidade para o primeiro item da lista. O status da tupla é
        de estoque ("Normal"/"Baixo"/"Crítico"), nunca "Inativo", então ele
        também não diz se o produto está ativo.
        """
        if isinstance(product, tuple):
            code, name, category, stock, sale_price, _stock_status = product
            unit = cost = None
            active = True
        else:
            code = product.code
            name = product.name
            category = product.category
            stock = product.stock
            sale_price = product.sale_price
            unit = product.unit
            cost = product.cost
            active = product.active

        self.code_input.setText(code)
        self.name_input.setText(name)
        self._selecionar(self.category_input, category)
        self._selecionar(self.unit_input, unit)
        self.initial_stock_input.setValue(_para_inteiro(stock))
        self.sale_price_input.setValue(valor_de_moeda(sale_price))
        self.cost_price_input.setValue(valor_de_moeda(cost))
        self.product_status_toggle.setChecked(bool(active))

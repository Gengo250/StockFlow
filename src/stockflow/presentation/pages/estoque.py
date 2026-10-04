import dataclasses

import qtawesome as qta
from PySide6.QtCore import QSize, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from stockflow.domain.stock_level import (
    ATTENTION,
    NORMAL,
    SEVERITY,
    derive_stock_status,
    is_below_minimum,
    to_int,
    to_min,
)
from stockflow.presentation.demo_products import DEMO_PRODUCTS
from stockflow.presentation.styles import inventory
from stockflow.presentation.widgets.stock_table import StockTable

# Índices da linha do modelo, NA ORDEM EM QUE A TABELA DESENHA. Os sete
# primeiros são as colunas de texto; `ACTIVE` fica no fim porque decide o
# rótulo da coluna de situação sem ser uma coluna própria.
#
# A linha é lista, não tupla: `apply_filters` reescreve o status no lugar.
CODE, NAME, CATEGORY, STOCK, MINIMUM, PRICE, STATUS, ACTIVE = range(8)

ALL = "Todos"
# A seleção que a US04 pede, em um clique: produtos ativos cujo saldo é menor
# ou igual ao mínimo CONFIGURADO. Quem não tem mínimo fica de fora porque
# `derive_stock_status` já o classifica como Normal.
#
# Existe como filtro próprio, e não como "clique em Baixo e depois em
# Crítico", porque a história pede UMA consulta — e porque as duas situações
# juntas são o que define "precisa de reposição".
BELOW_MINIMUM_FILTER = "Abaixo do mínimo"
INACTIVE_FILTER = "Inativos"
FILTERS = (ALL, BELOW_MINIMUM_FILTER, ATTENTION, NORMAL, INACTIVE_FILTER)

# Filtros que mostram problema. Neles a ordem de cadastro não serve: quem
# abre o alerta quer repor o pior primeiro.
SORTED_BY_CRITICALITY = frozenset({BELOW_MINIMUM_FILTER, ATTENTION})

# Estados da lista. "Pronto" não significa "tem linhas": significa que o que
# está na tela corresponde ao que a consulta devolveu.
READY = "ready"
LOADING = "loading"
ERROR = "error"


class EstoquePage(QWidget):
    product_edit_requested = Signal(object)
    # Avisa a janela que a situação de cadastro de um produto mudou, para que
    # as outras telas (Produtos, Vendas, ficha) reflitam. A página não as
    # alcança sozinha, e tentar alcançá-las daqui a faria conhecer a janela.
    product_status_changed = Signal(str)

    def __init__(self, products=None):
        """Monta a tela sobre o catálogo compartilhado `code -> Product`.

        Sem argumento a página cai em `DEMO_PRODUCTS`, para continuar
        utilizável isolada (telas de inspeção, testes de widget). O caminho
        que importa é o outro: a `MainWindow` passa o MESMO dict em que o
        repositório grava, e é isso que permite a `reload_products` redesenhar
        a tabela com o que acabou de ser salvo.
        """
        super().__init__()
        self.setObjectName("estoquePage")
        self.setStyleSheet(inventory.PAGE_QSS)
        # CÓPIA no caminho sem argumento, nunca o próprio `DEMO_PRODUCTS`:
        # `toggle_product_status` grava no catálogo, e gravar no dict do
        # módulo deixaria uma página isolada desativando o produto para o
        # processo inteiro — inclusive para as telas que nascerem depois.
        # O caminho compartilhado continua recebendo o MESMO dict da janela,
        # que é o que faz Estoque, Produtos e Vendas enxergarem a mudança.
        # Estado da lista. Sem ele, "zero linhas" seria ambíguo entre vazio,
        # carregando e falha — e qualquer heurística baseada em `rowCount`
        # mentiria em dois dos três casos.
        self._list_state = READY
        self.last_load_error = None

        self.products = dict(DEMO_PRODUCTS) if products is None else products
        self.produtos = self._build_rows()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(18)
        layout.addLayout(self._create_header())
        layout.addLayout(self._create_filters())
        # Nasce vazia: `apply_filters`, no fim do __init__, é quem popula.
        # Passar `self.produtos` aqui montaria a tabela inteira para ela ser
        # desmontada e remontada uma linha depois — o dobro de widgets de
        # ação criados e descartados em toda abertura da tela.
        self.stock_table = StockTable([])
        self.stock_table.product_edit_requested.connect(self.product_edit_requested.emit)
        self.stock_table.product_status_toggle_requested.connect(
            self.toggle_product_status
        )
        self.table = self.stock_table.table
        layout.addWidget(self.stock_table)

        # Os três estados que a tabela sozinha não consegue comunicar. Tabela
        # com zero linhas significa três coisas diferentes — nada corresponde
        # ao filtro, ainda está carregando, ou a consulta falhou — e sem
        # estes rótulos o usuário não distingue nenhuma delas.
        #
        # Ficam ABAIXO da tabela, no padrão de `ProductsPage.empty_message`,
        # e nunca a substituem no caminho normal: a tabela precisa continuar
        # existindo e sendo o mesmo widget, porque a janela e os testes
        # guardam a referência dela.
        self.list_state_label = QLabel()
        self.list_state_label.setObjectName("listState")
        self.list_state_label.setWordWrap(True)
        self.list_state_label.setStyleSheet(inventory.LIST_STATE_QSS)
        self.list_state_label.setVisible(False)
        layout.addWidget(self.list_state_label)

        self.load_error_label = QLabel()
        self.load_error_label.setObjectName("loadError")
        self.load_error_label.setWordWrap(True)
        self.load_error_label.setAccessibleName("Erro ao carregar o estoque")
        self.load_error_label.setStyleSheet(inventory.LOAD_ERROR_QSS)
        self.load_error_label.setVisible(False)
        layout.addWidget(self.load_error_label)

        self.apply_filters()

    # ======================================================
    # ESTADOS DA LISTA (SCRUM: preenchida, vazia, carregando, falha)
    # ======================================================

    def begin_loading(self):
        """Entra em "carregando" e tranca os controles.

        Busca e filtros são desabilitados de propósito: os dois chamam
        `apply_filters`, que recalcula sobre `self.produtos` — e durante a
        carga essa lista ainda é a ANTERIOR. Deixá-los ativos permitiria
        filtrar dados que estão prestes a ser substituídos.
        """
        self._list_state = LOADING
        self.last_load_error = None
        self._trancar_controles(True)
        self._render_list_state()

    def show_load_error(self, erro):
        """Falha de consulta, dita NA ÁREA DA LISTA e não num diálogo.

        Diálogo some quando fechado e deixa uma tabela vazia indistinguível
        de "não há produtos em alerta" — exatamente a confusão que o cartão
        manda eliminar. O estado precisa persistir enquanto a lista estiver
        sem dados confiáveis.
        """
        self._list_state = ERROR
        self.last_load_error = erro
        self._trancar_controles(False)
        self.load_error_label.setText(
            "Não foi possível carregar o estoque.\n\n"
            f"{erro}\n\nTente novamente em instantes."
        )
        self._render_list_state()

    def _trancar_controles(self, trancado: bool):
        self.search_input.setEnabled(not trancado)
        for button in self.filter_buttons:
            button.setEnabled(not trancado)

    def _render_list_state(self, visiveis=None):
        """Mostra o rótulo certo para o estado atual.

        A tabela só é escondida nos estados em que o conteúdo dela não vale
        nada (carregando e falha). No estado normal ela permanece visível
        mesmo vazia, como em `ProductsPage`: a grade com cabeçalho diz ao
        usuário o que ele está deixando de ver.
        """
        carregando = self._list_state == LOADING
        com_erro = self._list_state == ERROR

        self.load_error_label.setVisible(com_erro)
        self.stock_table.setVisible(not carregando and not com_erro)

        if carregando:
            self.list_state_label.setText("Carregando produtos...")
            self.list_state_label.setVisible(True)
            return
        if com_erro:
            self.list_state_label.setVisible(False)
            return

        vazio = not visiveis
        if vazio:
            self.list_state_label.setText(self._texto_de_lista_vazia())
        self.list_state_label.setVisible(bool(vazio))

    def _texto_de_lista_vazia(self) -> str:
        """Vazio por busca e vazio por não haver alerta são coisas diferentes.

        Dizer "nenhum produto em alerta" para quem digitou um termo que não
        casa com nada seria mentira — e esconderia que basta limpar a busca.
        """
        if self.search_input.text().strip():
            return "Nenhum produto corresponde à busca."
        filtro = self.current_filter()
        if filtro == BELOW_MINIMUM_FILTER:
            return (
                "Nenhum produto em alerta de estoque. "
                "Produtos sem mínimo configurado não entram nesta lista."
            )
        if filtro == INACTIVE_FILTER:
            return "Nenhum produto desativado."
        if filtro == ALL:
            return "Nenhum produto cadastrado."
        return f"Nenhum produto na situação \"{filtro}\"."

    def _build_rows(self):
        """Converte o catálogo nas linhas que a tela manipula.

        Listas, não tuplas: `apply_filters` reescreve o status no índice
        `STATUS` e `toggle_product_status` inverte `ACTIVE`. Com tupla, cada
        mudança criaria uma linha nova e as referências que a tabela e os
        botões guardam apontariam para a versão anterior.
        """
        return [
            [product.code, product.name, product.category, product.stock,
             getattr(product, "minimum_stock", None), product.sale_price,
             product.stock_status, bool(product.active)]
            for product in self.products.values()
        ]

    # ======================================================
    # BUSCA E FILTRO (US04)
    # ======================================================

    def current_filter(self) -> str:
        """Rótulo do filtro marcado. `Todos` quando nenhum está."""
        for button in self.filter_buttons:
            if button.isChecked():
                return button.text()
        return ALL

    def select_filter(self, selected_button):
        """Marca um filtro e redesenha. Os filtros são mutuamente exclusivos."""
        for button in self.filter_buttons:
            button.setChecked(button == selected_button)
        self.apply_filters()

    def apply_filters(self):
        """Recalcula o status de todas as linhas e redesenha as visíveis.

        O recálculo vem ANTES do filtro, e cobre o catálogo inteiro — não só
        o que está na tela. O status gravado na linha é cache: uma edição de
        estoque, uma importação ou um valor errado vindo do banco deixariam a
        coluna mentindo, e o filtro "Crítico" esconderia justamente o item
        que precisa aparecer. Por isso o valor da lista é sobrescrito, nunca
        consultado.
        """
        for row in self.produtos:
            row[STATUS] = derive_stock_status(row[STOCK], row[MINIMUM])
            # Só a AUSÊNCIA vira travessão. Mínimo zero é configuração real
            # e aparece como "0" — é essa diferença na própria célula que o
            # critério da US03 cobra, e escondê-la atrás do mesmo símbolo
            # deixaria o usuário sem saber por que um alerta e o outro não.
            if to_min(row[MINIMUM]) is None:
                row[MINIMUM] = "—"

        filtro = self.current_filter()
        busca = self.search_input.text().strip().casefold()

        visiveis = [
            row for row in self.produtos
            if self._combina_com_busca(row, busca)
            and self._combina_com_filtro(row, filtro)
        ]

        if filtro in SORTED_BY_CRITICALITY:
            # Pior situação primeiro e, dentro dela, menor saldo primeiro.
            # Ordenar só por saldo misturaria um crítico de 0 com um "baixo"
            # de 2 sem dizer qual é mais urgente.
            visiveis.sort(key=lambda row: (SEVERITY.get(row[STATUS], 9),
                                           to_int(row[STOCK])))

        self.stock_table.set_products(visiveis)
        self._render_list_state(visiveis)
        # A contagem acompanha o que está na tela, não o catálogo: dizer
        # "4 produtos cadastrados" sobre uma busca que devolveu um faria a
        # tela contradizer a si mesma.
        self.subtitle.setText(f"{len(visiveis)} produtos cadastrados")

    @staticmethod
    def _combina_com_busca(row, busca: str) -> bool:
        """Busca única sobre código, nome e categoria.

        Um campo só, e não um por coluna, porque quem procura não sabe de
        antemão se o que lembra é o SKU, o nome ou a categoria.
        """
        if not busca:
            return True
        alvo = f"{row[CODE]} {row[NAME]} {row[CATEGORY]}".casefold()
        return busca in alvo

    @staticmethod
    def _combina_com_filtro(row, filtro: str) -> bool:
        """Qual recorte cada filtro mostra.

        `Todos` significa TODOS, inativos inclusive. Esconder o desativado da
        lista completa fazia "desativar" parecer "excluir", e deixava sem
        resposta a pergunta mais comum depois de desativar: "cadê o produto
        que eu acabei de mexer?". Quem distingue um do outro é a coluna
        "Status do produto", não a ausência da linha.

        Os filtros de SITUAÇÃO DE ESTOQUE, por outro lado, só consideram
        ativos: situação de estoque é sobre repor, e repor não se aplica a
        produto fora de operação. É isso que faz `Abaixo do mínimo` atender
        ao critério da US04 de excluir inativos.
        """
        ativo = bool(row[ACTIVE])
        if filtro == INACTIVE_FILTER:
            return not ativo
        if filtro == ALL:
            return True
        if not ativo:
            return False
        if filtro == BELOW_MINIMUM_FILTER:
            return is_below_minimum(row[STATUS])
        return row[STATUS] == filtro

    def toggle_product_status(self, produto):
        """Inverte ativo/inativo do produto da linha (US02 + US04).

        Escreve nos DOIS lugares de propósito: na linha, que é o que a
        tabela desenha, e no catálogo compartilhado, que é o que Vendas
        consulta para montar a oferta. Atualizar só a linha deixaria a tela
        de Estoque mostrando "Inativo" enquanto a venda continuava aceitando
        o produto.

        A permissão NÃO é verificada aqui: o botão que chega até este método
        é desabilitado por `StockTable.set_actions_enabled`, aplicado a cada
        remontagem da tabela a partir do papel da sessão. Quando a gravação
        for para o banco, este caminho passa a chamar `fn_set_product_active`
        pelo serviço, e aí a recusa volta a ser do domínio — como na US01.
        """
        produto[ACTIVE] = not bool(produto[ACTIVE])

        code = produto[CODE]
        atual = self.products.get(code)
        if atual is not None:
            self.products[code] = dataclasses.replace(
                atual, active=produto[ACTIVE]
            )

        self.apply_filters()
        self.product_status_changed.emit(code)

    def reload_products(self, products=None):
        """Redesenha a tabela a partir do catálogo atual.

        As células são itens criados com o valor do produto no momento da
        montagem; não há caminho de atualização dentro de um
        `QTableWidgetItem` já posto na grade. Então refletir uma gravação é
        refazer as linhas — inclusive as de produtos que não mudaram, porque
        a ordem do catálogo pode ter mudado junto.

        Busca e filtro sobrevivem à recarga: são estado da tela, não do
        catálogo. Quem acabou de cadastrar um produto enquanto filtrava
        "Crítico" não espera que a lista inteira volte.

        A permissão do papel NÃO é reaplicada aqui de propósito: quem a
        guarda é a própria `StockTable`, que recria os botões. Reaplicá-la de
        fora criaria um segundo dono para a mesma regra, e o caminho que
        esquecesse de chamar devolveria as ações a quem não pode gravar.
        """
        if products is not None:
            self.products = products
        # Carga concluída: sai de "carregando"/"falha" e destranca os
        # controles. É este método que a janela chama quando a consulta
        # volta, então ele é o ponto natural para encerrar os dois estados.
        self._list_state = READY
        self.last_load_error = None
        self._trancar_controles(False)
        self.produtos = self._build_rows()
        self.apply_filters()

    def _create_header(self):
        layout = QHBoxLayout()
        container = QWidget()
        texts = QVBoxLayout(container)
        texts.setContentsMargins(0, 0, 0, 0)
        texts.setSpacing(2)
        title = QLabel("Controle de Estoque")
        title.setStyleSheet(inventory.TITLE_QSS)
        # Guardado como atributo porque a contagem muda a cada recarga.
        self.subtitle = QLabel(f"{len(self.produtos)} produtos cadastrados")
        self.subtitle.setStyleSheet(inventory.SUBTITLE_QSS)
        texts.addWidget(title)
        texts.addWidget(self.subtitle)
        self.new_product_button = QPushButton("Novo Produto")
        self.new_product_button.setIcon(qta.icon("fa5s.plus", color="white"))
        self.new_product_button.setIconSize(QSize(14, 14))
        self.new_product_button.setFixedHeight(40)
        self.new_product_button.setStyleSheet(inventory.NEW_BUTTON_QSS)
        layout.addWidget(container)
        layout.addStretch()
        layout.addWidget(self.new_product_button)
        return layout

    def _create_filters(self):
        layout = QHBoxLayout()
        layout.setSpacing(10)
        # Atributo, e não local: sem a referência, o campo existia na tela mas
        # ninguém o alcançava — era um widget decorativo, que não filtrava
        # nada por não ter `textChanged` ligado a lugar nenhum.
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Buscar produto ou código...")
        self.search_input.setAccessibleName("Buscar no estoque")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setFixedHeight(44)
        self.search_input.addAction(
            qta.icon("fa5s.search", color="#94A3B8"), QLineEdit.LeadingPosition
        )
        self.search_input.setStyleSheet(inventory.SEARCH_QSS)
        self.search_input.textChanged.connect(self.apply_filters)
        layout.addWidget(self.search_input, 1)
        self.filter_buttons = []
        for index, text in enumerate(FILTERS):
            button = QPushButton(text)
            button.setCheckable(True)
            button.setFixedHeight(44)
            button.setMinimumWidth(82)
            button.setStyleSheet(inventory.FILTER_QSS)
            button.setChecked(index == 0)
            button.clicked.connect(lambda checked=False, btn=button: self.select_filter(btn))
            self.filter_buttons.append(button)
            layout.addWidget(button)
        return layout

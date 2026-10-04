"""US03 — consultar saldo, mínimo e situação, e localizar um produto.

Busca, filtros e ativar/desativar na tela de Estoque.

A regra de situação vive em `domain/stock_level.py` e é tradução literal de
`public.fn_stock_state`. Os números deste arquivo saem do catálogo de
demonstração, montado para cobrir uma faixa por produto:

    PRD-009  saldo 18  mínimo 10  Normal
    PRD-008  saldo  6  mínimo 10  Baixo
    PRD-007  saldo  2  mínimo  5  Baixo
    PRD-006  saldo  0  mínimo 10  Crítico
    PRD-005  saldo 11  mínimo 10  Atenção
    PRD-003  saldo  3  SEM mínimo Normal    <- ausente nunca alerta
    PRD-002  saldo  0  mínimo  0  Crítico   <- zero alerta ao acabar
"""

from stockflow.presentation.pages.estoque import MINIMUM, STATUS
from stockflow.presentation.widgets.stock_table import ACTIVE_COLUMN as ACTIVE


def visiveis(page):
    """Códigos atualmente renderizados na tabela."""
    return [
        page.table.item(row, 0).text()
        for row in range(page.table.rowCount())
    ]


def clicar_filtro(page, texto):
    for button in page.filter_buttons:
        if button.text() == texto:
            button.click()
            return button
    raise AssertionError(f"filtro '{texto}' não existe")


def celula(page, codigo, coluna):
    linha = visiveis(page).index(codigo)
    return page.table.item(linha, coluna).text()


# ---------------------------------------------------------------- consulta


def test_estado_inicial_mostra_todos_os_produtos_ativos(estoque_page):
    assert visiveis(estoque_page) == [
        "PRD-009", "PRD-008", "PRD-007", "PRD-006", "PRD-005", "PRD-003", "PRD-002",
    ]
    assert estoque_page.subtitle.text() == "7 produtos cadastrados"


def test_a_consulta_traz_saldo_minimo_e_situacao(estoque_page):
    """US03: a tela precisa mostrar os três, não só o saldo.

    Sem a coluna de mínimo, "Baixo" é um rótulo sem referência — o usuário
    não tem como saber baixo em relação a quê, nem decidir quanto repor.
    """
    assert celula(estoque_page, "PRD-007", 3) == "2"        # saldo
    assert celula(estoque_page, "PRD-007", MINIMUM) == "5"  # mínimo
    assert celula(estoque_page, "PRD-007", STATUS) == "Baixo"


def test_minimo_ausente_e_minimo_zero_sao_distinguiveis_na_celula(estoque_page):
    """US03: a coluna precisa dizer qual é qual.

    Os dois produtos têm saldo baixo e nenhum limiar positivo. Mostrar o
    mesmo símbolo nos dois deixaria o usuário sem entender por que um alerta
    e o outro não.
    """
    assert celula(estoque_page, "PRD-003", MINIMUM) == "—"     # ausente
    assert celula(estoque_page, "PRD-002", MINIMUM) == "0"     # configurado

    assert celula(estoque_page, "PRD-003", STATUS) == "Normal"
    assert celula(estoque_page, "PRD-002", STATUS) == "Crítico"


def test_a_celula_de_minimo_sobrevive_a_varias_leituras(estoque_page):
    """`apply_filters` reescreve a própria célula e relê na chamada seguinte.

    A tela chama `apply_filters` a cada tecla digitada na busca. Se o
    travessão não fosse reconhecido como ausência na releitura, o produto
    mudaria de situação no meio de uma digitação.
    """
    for _ in range(3):
        estoque_page.apply_filters()
    assert celula(estoque_page, "PRD-003", MINIMUM) == "—"
    assert celula(estoque_page, "PRD-003", STATUS) == "Normal"


# ------------------------------------------------------------------ busca


def test_busca_por_nome(estoque_page):
    estoque_page.search_input.setText("teclado")
    assert visiveis(estoque_page) == ["PRD-008"]


def test_busca_por_codigo(estoque_page):
    estoque_page.search_input.setText("PRD-007")
    assert visiveis(estoque_page) == ["PRD-007"]


def test_busca_por_categoria(estoque_page):
    estoque_page.search_input.setText("periféricos")
    assert visiveis(estoque_page) == ["PRD-008", "PRD-007"]


def test_busca_e_case_insensitive_e_ignora_espacos(estoque_page):
    estoque_page.search_input.setText("   MONITOR  ")
    assert visiveis(estoque_page) == ["PRD-009"]


def test_busca_sem_resultado(estoque_page):
    estoque_page.search_input.setText("xyz-inexistente")
    assert visiveis(estoque_page) == []
    assert estoque_page.subtitle.text() == "0 produtos cadastrados"


def test_limpar_busca_restaura_lista(estoque_page):
    estoque_page.search_input.setText("teclado")
    estoque_page.search_input.setText("")
    assert len(visiveis(estoque_page)) == 7


# ---------------------------------------------------------------- filtros


def test_filtro_normal(estoque_page):
    clicar_filtro(estoque_page, "Normal")
    # PRD-003 entra por não ter mínimo configurado: sem limiar, não alerta.
    assert visiveis(estoque_page) == ["PRD-009", "PRD-003"]


def test_filtro_atencao(estoque_page):
    """Faixa de aproximação: acima do mínimo, a menos de 20% dele."""
    clicar_filtro(estoque_page, "Atenção")
    assert visiveis(estoque_page) == ["PRD-005"]


def test_filtro_abaixo_do_minimo(estoque_page):
    clicar_filtro(estoque_page, "Abaixo do mínimo")
    # PRD-002 entra por ter mínimo ZERO configurado e saldo zerado.
    assert sorted(visiveis(estoque_page)) == [
        "PRD-002", "PRD-006", "PRD-007", "PRD-008",
    ]


def test_filtros_sao_mutuamente_exclusivos(estoque_page):
    clicar_filtro(estoque_page, "Normal")
    clicar_filtro(estoque_page, "Abaixo do mínimo")
    marcados = [b.text() for b in estoque_page.filter_buttons if b.isChecked()]
    assert marcados == ["Abaixo do mínimo"]


def test_busca_e_filtro_combinam(estoque_page):
    clicar_filtro(estoque_page, "Abaixo do mínimo")
    estoque_page.search_input.setText("mouse")
    assert visiveis(estoque_page) == ["PRD-007"]


# ----------------------------------------------- ativar / desativar (US02)


def test_desativar_mantem_na_lista_e_marca_o_status(estoque_page):
    """Desativar não é excluir — e a lista precisa dizer a diferença.

    O produto continua em "Todos", com a situação de ESTOQUE preservada e a
    situação de CADASTRO numa coluna própria. Sumir da lista fazia "desativar"
    parecer "excluir" e escondia o saldo de quem decidiria reativá-lo.
    """
    produto = estoque_page.produtos[1]          # PRD-008, Baixo
    estoque_page.toggle_product_status(produto)

    assert "PRD-008" in visiveis(estoque_page)
    linha = visiveis(estoque_page).index("PRD-008")
    assert estoque_page.table.item(linha, STATUS).text() == "Baixo"
    assert estoque_page.table.item(linha, ACTIVE).text() == "Inativo"


def test_filtro_inativos_isola_os_desativados(estoque_page):
    estoque_page.toggle_product_status(estoque_page.produtos[1])   # PRD-008

    clicar_filtro(estoque_page, "Inativos")
    assert visiveis(estoque_page) == ["PRD-008"]


def test_reativar_devolve_produto_para_a_lista(estoque_page):
    produto = estoque_page.produtos[1]
    estoque_page.toggle_product_status(produto)
    estoque_page.toggle_product_status(produto)
    assert "PRD-008" in visiveis(estoque_page)


def test_filtro_de_situacao_nao_mostra_inativos(estoque_page):
    produto = estoque_page.produtos[2]          # PRD-007, Baixo
    estoque_page.toggle_product_status(produto)
    clicar_filtro(estoque_page, "Abaixo do mínimo")
    assert sorted(visiveis(estoque_page)) == ["PRD-002", "PRD-006", "PRD-008"]


def test_botao_de_acao_alterna_o_status(estoque_page):
    """Clica no botão real da célula de ações da primeira linha."""
    acoes = estoque_page.table.columnCount() - 1
    actions = estoque_page.table.cellWidget(0, acoes)
    toggle = actions.layout().itemAt(1).widget()
    assert toggle.toolTip() == "Desativar produto"
    toggle.click()
    assert estoque_page.produtos[0][-1] is False

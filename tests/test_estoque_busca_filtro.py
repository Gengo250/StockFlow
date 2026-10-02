"""Commit 4fab981 - feat(stock): product search, filtering and status toggle."""


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


# ---------------------------------------------------------------- busca

def test_estado_inicial_mostra_todos_os_produtos_ativos(estoque_page):
    assert visiveis(estoque_page) == ["PRD-009", "PRD-008", "PRD-007", "PRD-006"]
    assert estoque_page.subtitle.text() == "4 produtos cadastrados"


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
    assert len(visiveis(estoque_page)) == 4


# -------------------------------------------------------------- filtros

def test_filtro_normal(estoque_page):
    clicar_filtro(estoque_page, "Normal")
    assert visiveis(estoque_page) == ["PRD-009"]


def test_filtro_baixo(estoque_page):
    clicar_filtro(estoque_page, "Baixo")
    assert visiveis(estoque_page) == ["PRD-008"]


def test_filtro_critico(estoque_page):
    clicar_filtro(estoque_page, "Crítico")
    assert sorted(visiveis(estoque_page)) == ["PRD-006", "PRD-007"]


def test_filtros_sao_mutuamente_exclusivos(estoque_page):
    clicar_filtro(estoque_page, "Baixo")
    clicar_filtro(estoque_page, "Crítico")
    marcados = [b.text() for b in estoque_page.filter_buttons if b.isChecked()]
    assert marcados == ["Crítico"]


def test_busca_e_filtro_combinam(estoque_page):
    clicar_filtro(estoque_page, "Crítico")
    estoque_page.search_input.setText("mouse")
    assert visiveis(estoque_page) == ["PRD-007"]


# ----------------------------------------------- ativar / desativar (US)

def test_desativar_remove_de_todos_e_joga_em_inativos(estoque_page):
    produto = estoque_page.produtos[1]          # PRD-008
    estoque_page.toggle_product_status(produto)

    assert "PRD-008" not in visiveis(estoque_page)

    clicar_filtro(estoque_page, "Inativos")
    assert visiveis(estoque_page) == ["PRD-008"]
    assert estoque_page.table.item(0, 5).text() == "Inativo"


def test_reativar_devolve_produto_para_a_lista(estoque_page):
    produto = estoque_page.produtos[1]
    estoque_page.toggle_product_status(produto)
    estoque_page.toggle_product_status(produto)
    assert "PRD-008" in visiveis(estoque_page)


def test_filtro_de_status_nao_mostra_inativos(estoque_page):
    produto = estoque_page.produtos[2]          # PRD-007, Crítico
    estoque_page.toggle_product_status(produto)
    clicar_filtro(estoque_page, "Crítico")
    assert visiveis(estoque_page) == ["PRD-006"]


def test_botao_de_acao_alterna_o_status(estoque_page):
    """Clica no botão real da célula de ações da primeira linha."""
    actions = estoque_page.table.cellWidget(0, 6)
    toggle = actions.layout().itemAt(1).widget()
    assert toggle.toolTip() == "Desativar produto"
    toggle.click()
    assert estoque_page.produtos[0][6] is False

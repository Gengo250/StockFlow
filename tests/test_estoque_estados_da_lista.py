"""SCRUM — a tela de alerta apresenta lista preenchida, vazia e falha.

O cartão pede três apresentações distintas, mais feedback de carregamento.
Sem elas, uma tabela com zero linhas significa três coisas diferentes — nada
corresponde ao filtro, ainda está carregando, ou a consulta falhou — e o
usuário não tem como distinguir nenhuma.

ATENÇÃO AO `isVisible` NESTES TESTES: a fixture `estoque_page`
(`tests/conftest.py`) devolve a página SEM chamar `show()`. Num widget não
exibido, `isVisible()` é sempre `False`, então um teste escrito com ele
passaria ou falharia por motivo errado. Use `isVisibleTo(pai)`, que responde
"estaria visível se o pai estivesse".
"""

import pytest

from stockflow.presentation.pages.estoque import ERROR, LOADING, READY

from test_estoque_busca_filtro import clicar_filtro, visiveis


def mostrando(page, label) -> bool:
    return label.isVisibleTo(page)


# ------------------------------------------------------- lista preenchida


def test_lista_preenchida_nao_mostra_nenhum_aviso(estoque_page):
    assert visiveis(estoque_page), "o catálogo de demonstração veio vazio"
    assert not mostrando(estoque_page, estoque_page.list_state_label)
    assert not mostrando(estoque_page, estoque_page.load_error_label)
    assert mostrando(estoque_page, estoque_page.stock_table)


# ------------------------------------------------------------ lista vazia


def test_lista_vazia_por_busca_explica_a_busca(estoque_page):
    estoque_page.search_input.setText("xyz-inexistente")

    assert visiveis(estoque_page) == []
    assert mostrando(estoque_page, estoque_page.list_state_label)
    assert "busca" in estoque_page.list_state_label.text().casefold()
    # A tabela continua montada, com o cabeçalho dizendo o que falta.
    assert mostrando(estoque_page, estoque_page.stock_table)


def test_lista_vazia_de_alerta_explica_o_alerta(estoque_page):
    """Vazio por busca e vazio por não haver alerta são coisas diferentes.

    Dizer "nenhum produto em alerta" a quem digitou um termo sem resultado
    seria mentira, e esconderia que basta limpar a busca.
    """
    for produto in estoque_page.produtos:
        produto[4] = None               # ninguém tem mínimo -> ninguém alerta
    clicar_filtro(estoque_page, "Abaixo do mínimo")

    assert visiveis(estoque_page) == []
    texto = estoque_page.list_state_label.text().casefold()
    assert "alerta" in texto
    assert "mínimo configurado" in texto


def test_sair_do_vazio_esconde_o_aviso(estoque_page):
    estoque_page.search_input.setText("xyz-inexistente")
    assert mostrando(estoque_page, estoque_page.list_state_label)

    estoque_page.search_input.setText("")
    assert not mostrando(estoque_page, estoque_page.list_state_label)


# ------------------------------------------------------------ carregando


def test_carregando_troca_a_tabela_pelo_aviso(estoque_page):
    estoque_page.begin_loading()

    assert estoque_page._list_state == LOADING
    assert mostrando(estoque_page, estoque_page.list_state_label)
    assert "carregando" in estoque_page.list_state_label.text().casefold()
    # A tabela some: o conteúdo dela é o anterior e não vale nada agora.
    assert not mostrando(estoque_page, estoque_page.stock_table)


def test_carregando_tranca_busca_e_filtros(estoque_page):
    """Os dois chamam `apply_filters`, que recalcula sobre a lista ANTERIOR."""
    estoque_page.begin_loading()

    assert not estoque_page.search_input.isEnabled()
    assert not any(b.isEnabled() for b in estoque_page.filter_buttons)


def test_concluir_a_carga_devolve_a_tabela_e_os_controles(estoque_page):
    estoque_page.begin_loading()
    estoque_page.reload_products()

    assert estoque_page._list_state == READY
    assert mostrando(estoque_page, estoque_page.stock_table)
    assert estoque_page.search_input.isEnabled()
    assert all(b.isEnabled() for b in estoque_page.filter_buttons)


# ------------------------------------------------------- falha de consulta


def test_falha_aparece_na_area_da_lista_e_persiste(estoque_page):
    """Diálogo some ao ser fechado e deixa a tabela vazia sem explicação."""
    erro = RuntimeError("conexão recusada")
    estoque_page.show_load_error(erro)

    assert estoque_page._list_state == ERROR
    assert estoque_page.last_load_error is erro
    assert mostrando(estoque_page, estoque_page.load_error_label)
    assert "conexão recusada" in estoque_page.load_error_label.text()
    assert not mostrando(estoque_page, estoque_page.stock_table)


def test_falha_nao_se_disfarca_de_lista_vazia(estoque_page):
    """A confusão exata que o cartão manda eliminar."""
    estoque_page.show_load_error(RuntimeError("timeout"))

    assert mostrando(estoque_page, estoque_page.load_error_label)
    assert not mostrando(estoque_page, estoque_page.list_state_label)


def test_falha_destranca_os_controles(estoque_page):
    """Travar depois de falhar deixaria o usuário sem nada a fazer."""
    estoque_page.show_load_error(RuntimeError("timeout"))

    assert estoque_page.search_input.isEnabled()
    assert all(b.isEnabled() for b in estoque_page.filter_buttons)


def test_recarga_bem_sucedida_limpa_a_falha(estoque_page):
    estoque_page.show_load_error(RuntimeError("timeout"))
    estoque_page.reload_products()

    assert estoque_page._list_state == READY
    assert estoque_page.last_load_error is None
    assert not mostrando(estoque_page, estoque_page.load_error_label)
    assert mostrando(estoque_page, estoque_page.stock_table)


# ------------------------------------------- a tabela nunca é substituída


@pytest.mark.parametrize("acao", ["begin_loading", "show_load_error"])
def test_os_estados_nao_trocam_o_widget_da_tabela(estoque_page, acao):
    """`MainWindow` e os testes guardam `page.table` e `page.stock_table`.

    Esconder é seguro; recriar deixaria todas essas referências apontando
    para um widget fora da tela.
    """
    tabela, stock_table = estoque_page.table, estoque_page.stock_table

    if acao == "begin_loading":
        estoque_page.begin_loading()
    else:
        estoque_page.show_load_error(RuntimeError("x"))
    estoque_page.reload_products()

    assert estoque_page.table is tabela
    assert estoque_page.stock_table is stock_table
    assert estoque_page.table.rowCount() == len(estoque_page.produtos)

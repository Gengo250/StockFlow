"""Consulta do histórico de vendas pela tela (US17).

Exercita o caminho do usuário: mexer nos campos da tela e conferir o que a
tabela mostra. Nenhum teste aqui chama o repositório direto — o que se quer
provar é que a tela leva o filtro até a consulta e devolve o resultado.
"""

import pytest
from PySide6.QtCore import QDate
from PySide6.QtWidgets import QAbstractItemView

from stockflow.domain.enums.user_role import UserRole
from stockflow.infrastructure.repositories.demo_sale_repository import sale_row
from stockflow.presentation.demo_accounts import conta_por_papel
from stockflow.presentation.pages.vendas import VendasPage


def _venda(i):
    linha = sale_row(
        f"VND-{i:04d}",
        f"Cliente {i % 4}",
        ["PRD-001"],
        ["Produto"],
        10 + i,
        f"{(i % 28) + 1:02d}/10/2026 10:00",
    )
    linha.update(
        status="CANCELADA" if i == 3 else "CONCLUIDA",
        reversal_kind="CANCELAMENTO" if i == 3 else None,
        reversal_reason="registro em duplicidade" if i == 3 else None,
        client_id=f"c{i % 4}",
        seller_id="s1",
        seller="João Vendedor",
        payment_method="PIX",
        discount="0",
        items=[],
    )
    return linha


@pytest.fixture
def pagina(qapp):
    page = VendasPage(session=conta_por_papel(UserRole.ADMIN).session())
    page.service.repository.rows = [_venda(i) for i in range(120)]
    page.reload_sales()
    yield page
    page.close()


# ------------------------------------------------- SCRUM-218: paginação


def test_historico_mostra_uma_pagina_e_nao_tudo(pagina):
    assert pagina.table.rowCount() == 50
    assert pagina.paginacao_label.text() == "Página 1 de 3"


def test_rodape_diz_a_pagina_e_o_total_do_filtro(pagina):
    """Só o tamanho da página faria o usuário achar que o histórico tem 50."""
    assert "50 nesta página" in pagina.result_count.text()
    assert "120 venda(s)" in pagina.result_count.text()


def test_avancar_e_voltar_pagina_nao_repete_registro(pagina):
    primeira = [pagina.table.item(r, 0).text() for r in range(pagina.table.rowCount())]
    pagina.proximo_button.click()
    segunda = [pagina.table.item(r, 0).text() for r in range(pagina.table.rowCount())]
    assert not set(primeira) & set(segunda)
    pagina.anterior_button.click()
    assert [
        pagina.table.item(r, 0).text() for r in range(pagina.table.rowCount())
    ] == primeira


def test_primeira_pagina_desabilita_anterior(pagina):
    assert not pagina.anterior_button.isEnabled()
    assert pagina.proximo_button.isEnabled()


def test_ultima_pagina_desabilita_proximo(pagina):
    pagina.proximo_button.click()
    pagina.proximo_button.click()
    assert pagina.paginacao_label.text() == "Página 3 de 3"
    assert not pagina.proximo_button.isEnabled()
    assert pagina.anterior_button.isEnabled()


def test_as_tres_paginas_cobrem_o_historico_inteiro(pagina):
    vistos = []
    for _ in range(3):
        vistos += [pagina.table.item(r, 0).text() for r in range(pagina.table.rowCount())]
        if pagina.proximo_button.isEnabled():
            pagina.proximo_button.click()
    assert len(vistos) == 120
    assert len(set(vistos)) == 120


def test_ordem_padrao_e_da_mais_recente_para_a_mais_antiga(pagina):
    datas = [pagina.table.item(r, 4).text()[:10] for r in range(pagina.table.rowCount())]
    assert datas == sorted(datas, reverse=True)


# ------------------------------------- SCRUM-219: filtros e ordenação


def test_filtro_por_cliente_muda_a_lista_e_o_total(pagina):
    pagina.filtro_cliente.setCurrentIndex(pagina.filtro_cliente.findData("c1"))
    assert pagina.table.rowCount() == 30
    assert "30 venda(s)" in pagina.result_count.text()


def test_filtro_por_status_encontra_a_cancelada(pagina):
    pagina.filtro_status.setCurrentIndex(pagina.filtro_status.findData("CANCELADA"))
    assert pagina.table.rowCount() == 1
    assert pagina.table.item(0, 0).text() == "VND-0003"


def test_pendente_nao_entra_no_padrao_mas_pode_ser_consultada(pagina):
    pendente = _venda(120)
    pendente.update(id="VND-PENDENTE", status="PENDENTE")
    pagina.service.repository.rows.append(pendente)
    pagina.reload_sales()

    assert pagina._pagina.total == 120
    assert all(venda["status"] != "PENDENTE" for venda in pagina.historico_vendas)

    pagina.filtro_status.setCurrentIndex(
        pagina.filtro_status.findData("PENDENTE")
    )
    assert pagina.table.rowCount() == 1
    assert pagina.table.item(0, 0).text() == "VND-PENDENTE"


def test_filtro_por_vendedor(pagina):
    pagina.filtro_vendedor.setCurrentIndex(pagina.filtro_vendedor.findData("s1"))
    assert pagina.table.rowCount() == 50
    assert "120 venda(s)" in pagina.result_count.text()


def test_filtros_combinam(pagina):
    pagina.filtro_cliente.setCurrentIndex(pagina.filtro_cliente.findData("c3"))
    pagina.filtro_status.setCurrentIndex(pagina.filtro_status.findData("CANCELADA"))
    assert pagina.table.rowCount() == 1
    assert pagina.table.item(0, 0).text() == "VND-0003"


def test_filtro_por_id_casa_por_prefixo(pagina):
    pagina.filtro_id.setText("VND-0007")
    assert pagina.table.rowCount() == 1


def test_filtro_de_periodo_inclui_o_ultimo_dia(pagina):
    """"De 5 a 5 de outubro" tem que trazer o dia 5 inteiro."""
    dia = QDate(2026, 10, 5)
    pagina.filtro_inicio.setDate(dia)
    pagina.filtro_fim.setDate(dia)
    assert pagina.table.rowCount() > 0
    for linha in range(pagina.table.rowCount()):
        assert pagina.table.item(linha, 4).text().startswith("05/10/2026")


def test_filtro_sobrevive_a_paginacao(pagina):
    pagina.filtro_vendedor.setCurrentIndex(pagina.filtro_vendedor.findData("s1"))
    pagina.proximo_button.click()
    assert pagina.filtro_atual().seller_id == "s1"
    assert pagina.paginacao_label.text() == "Página 2 de 3"


def test_mudar_filtro_volta_para_a_primeira_pagina(pagina):
    """Ficar na página 5 de um filtro novo parece "não há vendas"."""
    pagina.proximo_button.click()
    assert pagina.anterior_button.isEnabled()
    pagina.filtro_cliente.setCurrentIndex(pagina.filtro_cliente.findData("c2"))
    assert not pagina.anterior_button.isEnabled()


def test_filtro_sobrevive_a_recarga(pagina):
    pagina.filtro_cliente.setCurrentIndex(pagina.filtro_cliente.findData("c1"))
    pagina.reload_sales()
    assert pagina.filtro_atual().client_id == "c1"
    assert pagina.table.rowCount() == 30


def test_limpar_filtros_restaura_a_lista_inteira(pagina):
    pagina.filtro_cliente.setCurrentIndex(pagina.filtro_cliente.findData("c1"))
    pagina.filtro_id.setText("VND")
    pagina.limpar_filtros_button.click()
    assert pagina.table.rowCount() == 50
    assert not pagina.filtro_atual().ativo


def test_ordenar_por_maior_valor(pagina):
    pagina.ordenacao_combo.setCurrentIndex(
        pagina.ordenacao_combo.findData("VALOR_DESC")
    )
    assert pagina.table.item(0, 0).text() == "VND-0119"


def test_ordenar_por_menor_valor(pagina):
    pagina.ordenacao_combo.setCurrentIndex(
        pagina.ordenacao_combo.findData("VALOR_ASC")
    )
    assert pagina.table.item(0, 0).text() == "VND-0000"


def test_busca_livre_filtra_apenas_a_pagina_carregada(pagina):
    """Ela é um recorte visual da página, e o rótulo diz isso."""
    pagina.search_input.setText("Cliente 1")
    visiveis = sum(
        not pagina.table.isRowHidden(r) for r in range(pagina.table.rowCount())
    )
    assert 0 < visiveis < 50
    assert "nesta página" in pagina.search_input.placeholderText()


def test_filtro_sem_resultado_explica_o_vazio(pagina):
    pagina.filtro_id.setText("NAO-EXISTE")
    assert pagina.table.rowCount() == 0
    assert "filtros" in pagina.empty_label.text()


# ---------------------------------- SCRUM-222/223: status e edição


def test_coluna_de_status_distingue_cancelada(pagina):
    cabecalhos = [
        pagina.table.horizontalHeaderItem(c).text()
        for c in range(pagina.table.columnCount())
    ]
    assert "Status" in cabecalhos
    pagina.filtro_status.setCurrentIndex(pagina.filtro_status.findData("CANCELADA"))
    coluna = cabecalhos.index("Status")
    assert pagina.table.item(0, coluna).text() == "Cancelada"


def test_filtro_padrao_identifica_a_listagem_de_vendas_finalizadas(pagina):
    assert pagina.filtro_status.itemText(0) == "Todas as vendas finalizadas"
    assert pagina.filtro_status.findData("PENDENTE") >= 0


def test_venda_cancelada_mostra_o_motivo_no_status(pagina):
    pagina.filtro_status.setCurrentIndex(pagina.filtro_status.findData("CANCELADA"))
    assert "registro em duplicidade" in pagina.table.item(0, 5).toolTip()


def test_venda_concluida_nao_inventa_motivo(pagina):
    pagina.filtro_status.setCurrentIndex(pagina.filtro_status.findData("CONCLUIDA"))
    assert pagina.table.item(0, 5).toolTip() == ""


def test_tabela_continua_sem_permitir_edicao(pagina):
    assert pagina.table.editTriggers() == QAbstractItemView.NoEditTriggers


def test_listagem_nao_oferece_cancelar_nem_devolver(pagina):
    """Ação destrutiva mora no detalhe, não na tabela densa."""
    acao = pagina.table.cellWidget(0, 6)
    assert acao is not None
    assert "detalhes" in acao.accessibleName().casefold()


def test_botao_de_detalhe_emite_o_identificador(pagina):
    pedidos = []
    pagina.detalhes_requested.connect(pedidos.append)
    esperado = pagina.table.item(0, 0).text()
    pagina.table.cellWidget(0, 6).click()
    assert pedidos == [esperado]

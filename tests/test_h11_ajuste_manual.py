"""H11 — ajuste manual conferido pelo caminho do usuário.

Um teste por critério de aceite:

1. permissão — ADMIN e STOCK ajustam; SELLER é recusado, e não só pelo botão
   escondido;
2. justificativa — motivo é obrigatório, e `OUTRO` exige texto; recusa não
   grava nada;
3. saldo resultante — depois do ajuste o saldo é EXATAMENTE o contado.

Mais os casos de borda que costumam escapar: contar zero, contar o mesmo, e o
saldo mudar entre a contagem e o clique.
"""

import pytest
from PySide6.QtWidgets import QMessageBox

from stockflow.application.dto.adjustment_input import AdjustmentInput
from stockflow.domain.enums.adjustment_reason import AdjustmentReason
from stockflow.domain.enums.user_role import UserRole
from stockflow.domain.exceptions.adjustment_errors import SaldoDesatualizadoError
from stockflow.domain.exceptions.permission_denied import PermissionDeniedError
from stockflow.presentation import backend
from stockflow.presentation.demo_accounts import conta_por_papel
from stockflow.presentation.windows.main_window import MainWindow

PODEM_AJUSTAR = [UserRole.ADMIN, UserRole.STOCK]


@pytest.fixture
def sem_dialogos(monkeypatch):
    """Silencia os QMessageBox modais, que travariam o teste no `exec()`."""
    chamadas = []
    monkeypatch.setattr(
        QMessageBox, "critical",
        staticmethod(lambda *args, **kwargs: chamadas.append(args)),
    )
    return chamadas


@pytest.fixture
def janela(qapp, monkeypatch, sem_dialogos):
    """Fábrica de MainWindow em modo demonstração, fechada no fim do teste."""
    monkeypatch.setenv("STOCKFLOW_BACKEND", "demo")
    monkeypatch.setattr(backend, "_demo_users", {})
    abertas = []

    def abrir(papel):
        # Sem `show_page`: para o SELLER isso dispara o redirecionamento de
        # navegação, que é assunto da H14. Aqui o que se mede é o ajuste, e o
        # card já nasce montado e com a permissão aplicada pela sessão.
        w = MainWindow(session=conta_por_papel(papel).session())
        abertas.append(w)
        return w

    yield abrir
    for w in abertas:
        w.close()


def primeiro_produto(w):
    codigo = next(iter(w.products))
    return codigo, int(w.products[codigo].stock)


def preencher(page, codigo, contado, motivo, detalhe=""):
    page.ajuste_produto_combo.setCurrentIndex(
        page.ajuste_produto_combo.findData(codigo)
    )
    page.ajuste_contado_input.setValue(contado)
    page.ajuste_motivo_combo.setCurrentIndex(
        page.ajuste_motivo_combo.findData(motivo)
    )
    page.ajuste_detalhe_input.setText(detalhe)


# ------------------------------------------------------------- 1. permissão


@pytest.mark.parametrize("papel", PODEM_AJUSTAR)
def test_admin_e_estoquista_ajustam_pelo_card(janela, papel):
    w = janela(papel)
    codigo, atual = primeiro_produto(w)

    preencher(w.movimentacoes_page, codigo, atual + 3, AdjustmentReason.CONTAGEM)
    w.movimentacoes_page.ajuste_aplicar_button.click()

    assert int(w.products[codigo].stock) == atual + 3


def test_o_vendedor_nao_ve_o_card_operavel(janela):
    w = janela(UserRole.SELLER)
    page = w.movimentacoes_page

    assert not page.ajuste_aplicar_button.isEnabled()
    assert not page.ajuste_contado_input.isEnabled()


def test_o_vendedor_e_recusado_mesmo_burlando_o_controle_visual(janela):
    """O critério não é "o botão some" — é que a gravação não aconteça.

    O serviço checa antes de tocar no repositório, e no banco
    `fn_register_adjustment` checa `fn_has_role` por conta própria. São
    camadas: esta dá a mensagem, aquela impede.
    """
    w = janela(UserRole.SELLER)
    codigo, atual = primeiro_produto(w)

    with pytest.raises(PermissionDeniedError):
        w.movement_service.adjust(w.session, AdjustmentInput(
            product_code=codigo, counted_balance=0, expected_balance=atual,
            reason=AdjustmentReason.PERDA,
        ))

    assert int(w.products[codigo].stock) == atual


# --------------------------------------------------------- 2. justificativa


def test_outro_sem_detalhe_nao_grava_nada(janela):
    w = janela(UserRole.STOCK)
    codigo, atual = primeiro_produto(w)
    page = w.movimentacoes_page

    preencher(page, codigo, atual - 1, AdjustmentReason.OUTRO, detalhe="")
    page.ajuste_aplicar_button.click()

    assert int(w.products[codigo].stock) == atual
    assert "justificativa" in page.warning_label.text().casefold()


def test_outro_com_detalhe_grava_e_o_detalhe_aparece_no_historico(janela):
    w = janela(UserRole.STOCK)
    codigo, atual = primeiro_produto(w)
    page = w.movimentacoes_page

    preencher(page, codigo, atual - 1, AdjustmentReason.OUTRO,
              detalhe="Caixa amassada na doca")
    page.ajuste_aplicar_button.click()

    assert int(w.products[codigo].stock) == atual - 1
    observacoes = [
        page.table.item(linha, 4).text() for linha in range(page.table.rowCount())
    ]
    assert "Caixa amassada na doca" in observacoes


def test_o_motivo_aparece_na_coluna_propria(janela):
    """Coluna Motivo, não Observação: motivo é dado agregável, nota é texto."""
    w = janela(UserRole.STOCK)
    codigo, atual = primeiro_produto(w)
    page = w.movimentacoes_page

    preencher(page, codigo, atual - 2, AdjustmentReason.QUEBRA)
    page.ajuste_aplicar_button.click()

    motivos = [
        page.table.item(linha, 7).text() for linha in range(page.table.rowCount())
    ]
    assert AdjustmentReason.QUEBRA.label in motivos


# ------------------------------------------------------ 3. saldo resultante


def test_o_saldo_final_e_exatamente_o_contado(janela):
    w = janela(UserRole.STOCK)
    codigo, _ = primeiro_produto(w)
    page = w.movimentacoes_page

    preencher(page, codigo, 7, AdjustmentReason.CONTAGEM)
    page.ajuste_aplicar_button.click()

    assert int(w.products[codigo].stock) == 7


def test_contar_zero_zera_o_saldo(janela):
    """Produto que sumiu inteiro: saída do saldo todo, resultante zero."""
    w = janela(UserRole.STOCK)
    codigo, _ = primeiro_produto(w)
    page = w.movimentacoes_page

    preencher(page, codigo, 0, AdjustmentReason.PERDA)
    page.ajuste_aplicar_button.click()

    assert int(w.products[codigo].stock) == 0


def test_contar_o_mesmo_numero_nao_registra_movimentacao(janela):
    w = janela(UserRole.STOCK)
    codigo, atual = primeiro_produto(w)
    page = w.movimentacoes_page
    linhas_antes = page.table.rowCount()

    preencher(page, codigo, atual, AdjustmentReason.CONTAGEM)

    assert not page.ajuste_aplicar_button.isEnabled()
    assert page.table.rowCount() == linhas_antes


def test_saldo_que_mudou_desde_a_contagem_pede_recontagem(janela):
    """A corrida real: a tela mostrou 42, outra pessoa confirmou uma entrada.

    Aplicar a diferença sobre o saldo novo daria um número que não é o
    contado nem o correto.
    """
    w = janela(UserRole.STOCK)
    codigo, atual = primeiro_produto(w)

    with pytest.raises(SaldoDesatualizadoError):
        w.movement_repository.adjust(AdjustmentInput(
            product_code=codigo, counted_balance=atual - 4,
            expected_balance=atual + 10,     # saldo que a tela teria exibido
            reason=AdjustmentReason.QUEBRA,
        ))

    assert int(w.products[codigo].stock) == atual


def test_a_recusa_de_recontagem_chega_ao_card_sem_dialogo(janela):
    """Erro na área do card, nunca em diálogo: diálogo some e some a razão."""
    w = janela(UserRole.STOCK)
    codigo, atual = primeiro_produto(w)

    w._aplicar_ajuste(AdjustmentInput(
        product_code=codigo, counted_balance=atual - 4,
        expected_balance=atual + 10, reason=AdjustmentReason.QUEBRA,
    ))

    assert "reconte" in w.movimentacoes_page.warning_label.text().casefold()
    assert int(w.products[codigo].stock) == atual

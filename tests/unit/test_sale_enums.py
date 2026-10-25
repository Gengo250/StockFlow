"""Os enums de venda espelham os tipos do banco (US17).

Enum de domínio que não acompanha `public.sale_status` deixa a tela montando
filtro por um rótulo que o Postgres recusa — e a recusa só aparece em
runtime, na consulta do usuário.
"""

import pytest

from stockflow.domain.enums.sale_reversal_kind import SaleReversalKind
from stockflow.domain.enums.sale_status import SaleStatus


def test_status_cobre_os_quatro_rotulos_do_banco():
    assert {s.value for s in SaleStatus} == {
        "PENDENTE",
        "CONCLUIDA",
        "CANCELADA",
        "DEVOLVIDA",
    }


def test_status_revertido_identifica_cancelada_e_devolvida():
    assert SaleStatus.CANCELADA.revertida
    assert SaleStatus.DEVOLVIDA.revertida
    assert not SaleStatus.CONCLUIDA.revertida
    assert not SaleStatus.PENDENTE.revertida


def test_so_a_concluida_e_reversivel():
    """É a mesma regra que `fn_cancel_sale` aplica no banco."""
    assert SaleStatus.CONCLUIDA.reversivel
    for outro in (SaleStatus.PENDENTE, SaleStatus.CANCELADA, SaleStatus.DEVOLVIDA):
        assert not outro.reversivel


def test_status_tem_rotulo_em_portugues():
    assert SaleStatus.DEVOLVIDA.label == "Devolvida"
    assert SaleStatus.CONCLUIDA.label == "Concluída"


def test_from_value_normaliza_texto_do_banco():
    assert SaleStatus.from_value(" concluida ") is SaleStatus.CONCLUIDA
    assert SaleStatus.from_value(SaleStatus.DEVOLVIDA) is SaleStatus.DEVOLVIDA


@pytest.mark.parametrize("entrada", ["ESTORNADA", "", None, 7])
def test_from_value_recusa_desconhecido(entrada):
    with pytest.raises(ValueError):
        SaleStatus.from_value(entrada)


def test_especie_de_reversao_tem_os_dois_valores_com_rotulo():
    assert {k.value for k in SaleReversalKind} == {"CANCELAMENTO", "DEVOLUCAO"}
    assert SaleReversalKind.DEVOLUCAO.label == "Devolução"
    assert SaleReversalKind.CANCELAMENTO.label == "Cancelamento"


def test_especie_from_value_recusa_desconhecido():
    with pytest.raises(ValueError):
        SaleReversalKind.from_value("ESTORNO")

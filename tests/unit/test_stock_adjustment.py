"""A aritmética do ajuste manual tem um dono só (H11).

A tela mostra "→ SAÍDA de 4" enquanto o usuário digita e o serviço valida o
mesmo antes de ir à rede. Se cada um calculasse por conta própria, seria a
repetição que fez a UI divergir de `fn_stock_state` em 5 de 11 casos antes
da US03 — a tela dizia `Crítico` onde o SQL dizia `Baixo`.
"""

import pytest

from stockflow.domain.enums.adjustment_reason import AdjustmentReason
from stockflow.domain.enums.movement_kind import MovementKind
from stockflow.domain.exceptions.adjustment_errors import (
    AjusteSemEfeitoError,
    SaldoDesatualizadoError,
)
from stockflow.domain.stock_adjustment import calcular_ajuste


def test_contado_maior_vira_entrada_da_diferenca():
    assert calcular_ajuste(42, 50) == (MovementKind.ENTRADA, 8)


def test_contado_menor_vira_saida_da_diferenca():
    assert calcular_ajuste(42, 38) == (MovementKind.SAIDA, 4)


def test_contar_zero_sobre_saldo_positivo_e_ajuste_valido():
    """Zerar o saldo é ajuste legítimo, não erro de digitação.

    É o caso do produto que sumiu inteiro da prateleira, e a saída de 5
    deixa o saldo em zero — dentro do `CHECK (stock >= 0)` de `products`.
    """
    assert calcular_ajuste(5, 0) == (MovementKind.SAIDA, 5)


def test_contado_igual_ao_atual_nao_gera_movimentacao():
    """Diferença zero não vira linha: `CHECK (quantity > 0)` a recusaria.

    Recusar aqui, com nome próprio, é o que permite à tela desabilitar o
    botão antes do clique em vez de traduzir um erro do Postgres.
    """
    with pytest.raises(AjusteSemEfeitoError):
        calcular_ajuste(42, 42)


def test_contado_negativo_e_recusado():
    with pytest.raises(ValueError):
        calcular_ajuste(42, -1)


def test_so_outro_exige_detalhe():
    assert AdjustmentReason.OUTRO.exige_detalhe is True
    assert [r for r in AdjustmentReason if r.exige_detalhe] == [AdjustmentReason.OUTRO]


def test_motivo_desconhecido_estoura_com_o_valor_na_mensagem():
    with pytest.raises(ValueError, match="INVENTADO"):
        AdjustmentReason.from_value("INVENTADO")


def test_motivo_aceita_o_proprio_enum_e_texto_cru():
    assert AdjustmentReason.from_value("quebra") is AdjustmentReason.QUEBRA
    assert AdjustmentReason.from_value(AdjustmentReason.PERDA) is AdjustmentReason.PERDA


def test_saldo_desatualizado_diz_os_dois_numeros():
    erro = SaldoDesatualizadoError.de_saldos(esperado=42, atual=45)

    assert "42" in str(erro) and "45" in str(erro)
    assert isinstance(erro, ValueError)

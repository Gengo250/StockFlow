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
from stockflow.domain.stock_adjustment import calcular_ajuste, saldo_contado


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


def test_os_seis_rotulos_sao_exatamente_estes():
    """Os rótulos são LITERAIS aqui, e não `AdjustmentReason.X.label`.

    Comparar o rótulo com ele mesmo é tautologia: trocar "Quebra / avaria"
    por "Perda / furto" no dicionário do enum deixaria o combo oferecendo o
    rótulo errado para cada valor, o operador registraria o motivo errado em
    todo ajuste, e o agregado que a lista fechada existe para produzir
    ("quanto sumiu por quebra neste mês") ficaria corrompido — com a suíte
    verde do começo ao fim.
    """
    assert {motivo.value: motivo.label for motivo in AdjustmentReason} == {
        "CONTAGEM": "Erro de contagem",
        "QUEBRA": "Quebra / avaria",
        "PERDA": "Perda / furto",
        "VENCIMENTO": "Vencimento",
        "DEVOLUCAO": "Devolução de cliente",
        "OUTRO": "Outro",
    }


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


# ------------------------------------- o saldo contado não ganha um padrão


def test_saldo_contado_converte_texto_de_formulario():
    """O campo da tela entrega inteiro, mas o DTO atravessa adaptador e rede."""
    assert saldo_contado(38) == 38
    assert saldo_contado(" 38 ") == 38
    assert saldo_contado(0) == 0


@pytest.mark.parametrize("valor", [None, "", "   ", "trinta", "38,5", "38.0"])
def test_saldo_contado_recusa_em_vez_de_devolver_zero(valor):
    """`to_int` devolveria `0` — e `0` é a contagem que ESVAZIA o produto.

    O padrão zero existe para que uma célula ilegível não derrube uma
    listagem. Aqui o número não é exibido: é o que decide quanto estoque
    sai, e um campo que não chegou não pode virar a ordem de zerar o saldo.
    """
    with pytest.raises(ValueError):
        saldo_contado(valor)

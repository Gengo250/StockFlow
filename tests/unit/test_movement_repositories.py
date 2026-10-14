"""Os dois adaptadores de movimentação, contra o cliente falso e contra o dict.

Não há Postgres neste ambiente, então o que estes testes provam do adaptador
de banco é o CONTRATO: qual função ele chama, com quais argumentos, quantas
consultas gasta e como traduz a resposta. É onde um adaptador erra — mandar o
código onde a função espera o uuid, resolver o produto linha a linha, deixar
uma recusa subir crua.

Do adaptador de demonstração o que se prova é mais forte, porque ele É a
implementação inteira: que PENDENTE não mexe no saldo e CONFIRMADA mexe. Essa
é a distinção da US03, e no modo demonstração não existe trigger para
garanti-la.

O cliente falso é o MESMO de `test_supabase_product_repository`. Reusar em vez
de recriar não é economia: duas imitações do cliente divergem, e a que o
teste novo escrevesse poderia aceitar um encadeamento que a real recusa.
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from stockflow.application.dto.movement_input import MovementInput
from stockflow.domain.enums.movement_kind import MovementKind
from stockflow.domain.enums.movement_status import MovementStatus
from stockflow.domain.exceptions.permission_denied import PermissionDeniedError
from stockflow.infrastructure.repositories.demo_movement_repository import (
    DemoMovementRepository,
)
from stockflow.infrastructure.repositories.movement_mapper import VAZIO
from stockflow.infrastructure.repositories.supabase_movement_repository import (
    SupabaseMovementRepository,
)
from stockflow.presentation.demo_products import Product

from test_supabase_product_repository import (
    COMPANY,
    PRODUTO_ID,
    ClienteFalso,
    ErroDoPostgrest,
    catalogo_falso,
)

OUTRO_PRODUTO_ID = "44444444-4444-4444-4444-444444444444"
MOV_ID = "55555555-5555-5555-5555-555555555555"

# Referência fixa de "agora". Sem ela, o teste da coluna de data passaria hoje
# e falharia na virada do dia, e dependeria do fuso da máquina que rodasse a
# suíte — foi por isso que `formatar_ultimo_acesso` ganhou o parâmetro.
AGORA = datetime(2026, 10, 3, 18, 30)
ONTEM = AGORA - timedelta(days=1)


# ------------------------------------------------------------------ fixtures


def movimentos_falsos(tabelas=None):
    """Catálogo do cliente falso acrescido de duas movimentações.

    A segunda aponta para um produto que NÃO está em `products`: é o caso em
    que a RLS de `products` filtra o que a de `stock_movements` deixou passar,
    e a tela precisa abrir mesmo assim.
    """
    tabelas = tabelas or catalogo_falso()
    tabelas["stock_movements"] = [
        {"id": MOV_ID, "company_id": COMPANY, "product_id": PRODUTO_ID,
         "kind": "ENTRADA", "quantity": 12, "status": "PENDENTE",
         "note": "Compra NF 4821", "created_on": ONTEM, "confirmed_on": None},
        {"id": "mov-2", "company_id": COMPANY, "product_id": OUTRO_PRODUTO_ID,
         "kind": "SAIDA", "quantity": 3, "status": "CONFIRMADA",
         "note": None, "created_on": AGORA, "confirmed_on": AGORA},
    ]
    return tabelas


def repositorio(cliente=None, **kwargs):
    kwargs.setdefault("agora", AGORA)
    return SupabaseMovementRepository(
        cliente or ClienteFalso(movimentos_falsos()), COMPANY, **kwargs
    )


def entrada(**overrides):
    base = dict(product_code="PRD-009", kind=MovementKind.ENTRADA, quantity=12,
                note="Compra NF 4821", confirm=False)
    base.update(overrides)
    return MovementInput(**base)


def args_de(cliente, nome):
    return next(a for n, a in cliente.chamadas_rpc if n == nome)


def catalogo_demo(stock="18", minimum_stock=10):
    return {
        "PRD-009": Product('PRD-009', 'Monitor LG UltraWide 34"', 'Eletrônicos',
                           'Unidade (UN)', 'R$ 2.499,90', 'R$ 1.850,00', True,
                           stock, 'Normal', minimum_stock=minimum_stock),
    }


# ======================================================
# Supabase — leitura
# ======================================================


def test_a_linha_do_banco_vira_a_tupla_que_a_tela_desenha():
    linhas = repositorio().list_movements()
    # Da mais recente para a mais antiga: a de hoje antes da de ontem.
    recente, antiga = linhas

    assert antiga == (
        MOV_ID,                 # o id vai na linha; confirmar/cancelar dependem dele
        "PRD-009",              # product_id resolvido para o código da tela
        'Monitor LG UltraWide 34"',
        "Entrada",              # enum traduzido por MovementKind.label
        12,                     # inteiro positivo; o sinal mora na espécie
        "Pendente",             # enum traduzido por MovementStatus.label
        "Compra NF 4821",
        "Ontem, 18:30",
        VAZIO,                  # sem fornecedor: posição fixa, nunca ausente
        VAZIO,                  # sem motivo de ajuste: idem
    )
    assert recente[0] == "mov-2"
    assert recente[7] == "Hoje, 18:30"


def test_produto_fora_do_alcance_vira_travessao_em_vez_de_erro():
    """A RLS de `products` pode filtrar o que a de movimentações deixou passar.

    Isso é informação faltando numa célula, não motivo para a tela não abrir.
    """
    recente = repositorio().list_movements()[0]
    assert recente[1] == VAZIO and recente[2] == VAZIO
    assert recente[6] == VAZIO  # nota NULL também


def test_canceladas_continuam_na_listagem():
    """Esconder a cancelada tiraria a resposta para "por que o saldo voltou?"."""
    tabelas = movimentos_falsos()
    tabelas["stock_movements"][0]["status"] = "CANCELADA"
    linhas = repositorio(ClienteFalso(tabelas)).list_movements()
    assert any(linha[5] == "Cancelada" for linha in linhas)


def test_toda_leitura_e_escopada_pela_empresa():
    cliente = ClienteFalso(movimentos_falsos())
    repositorio(cliente).list_movements()

    assert cliente.consultas, "nenhuma consulta registrada"
    assert all(f.get("company_id") == COMPANY for _, f in cliente.consultas)


def test_produtos_sao_resolvidos_em_uma_consulta_so():
    """N+1 aqui é uma ida à rede por movimentação para abrir a tela."""
    tabelas = movimentos_falsos()
    # Três movimentações, dois produtos distintos: o conjunto de ids também
    # tem que tirar a repetição, senão a consulta cresce com o histórico.
    tabelas["stock_movements"].append(
        {"id": "mov-3", "company_id": COMPANY, "product_id": PRODUTO_ID,
         "kind": "SAIDA", "quantity": 1, "status": "CONFIRMADA",
         "note": "", "created_on": AGORA, "confirmed_on": AGORA}
    )
    cliente = ClienteFalso(tabelas)
    repositorio(cliente).list_movements()

    assert sum(1 for t, _ in cliente.consultas if t == "products") == 1


def test_filtro_por_produto_traduz_o_codigo_para_uuid():
    cliente = ClienteFalso(movimentos_falsos())
    linhas = repositorio(cliente).list_movements("PRD-009")

    assert [linha[0] for linha in linhas] == [MOV_ID]
    filtros = [f for t, f in cliente.consultas if t == "stock_movements"]
    assert filtros and filtros[0]["product_id"] == PRODUTO_ID


def test_filtro_por_codigo_inexistente_nao_traz_o_historico_inteiro():
    """Sem o desvio, o filtro sumiria e a tela mostraria tudo da empresa."""
    cliente = ClienteFalso(movimentos_falsos())
    assert repositorio(cliente).list_movements("PRD-404") == ()
    assert not any(t == "stock_movements" for t, _ in cliente.consultas)


def test_leitura_alimenta_o_cache_de_traducao():
    """Quem acabou de ver o histórico de um produto é quem vai movimentá-lo."""
    cliente = ClienteFalso(movimentos_falsos())
    repo = repositorio(cliente)
    repo.list_movements()
    consultas_antes = len(cliente.consultas)

    repo.register(entrada())

    assert sum(1 for t, _ in cliente.consultas[consultas_antes:] if t == "products") == 0


# ======================================================
# Supabase — escrita
# ======================================================


def test_register_chama_a_funcao_com_os_tipos_do_banco():
    cliente = ClienteFalso(
        movimentos_falsos(), rpc_resultados={"fn_register_movement": MOV_ID}
    )
    assert repositorio(cliente).register(entrada()) == MOV_ID

    assert args_de(cliente, "fn_register_movement") == {
        "p_company_id": COMPANY,
        "p_product_id": PRODUTO_ID,   # uuid, não o código da tela
        "p_kind": "ENTRADA",          # valor do enum
        "p_quantity": 12,             # inteiro, não "12"
        "p_note": "Compra NF 4821",
        "p_confirm": False,           # registrar não é confirmar
    }


def test_register_com_confirmacao_pede_a_confirmacao_na_propria_funcao():
    """Um atalho de uma chamada, não um register seguido de confirm.

    Dois passos deixariam a janela entre eles observável: a movimentação
    apareceria pendente para quem listasse no meio.
    """
    cliente = ClienteFalso(
        movimentos_falsos(), rpc_resultados={"fn_register_movement": MOV_ID}
    )
    repositorio(cliente).register(entrada(confirm=True))

    assert args_de(cliente, "fn_register_movement")["p_confirm"] is True
    assert not any(n == "fn_confirm_movement" for n, _ in cliente.chamadas_rpc)


def test_compra_chama_funcao_que_valida_fornecedor_e_associa_historico():
    client = ClienteFalso(
        movimentos_falsos(),
        rpc_resultados={"fn_register_supplier_movement": MOV_ID},
    )
    data = entrada(supplier_id="supplier-1")
    assert repositorio(client).register(data) == MOV_ID
    assert client.chamadas_rpc[-1] == (
        "fn_register_supplier_movement",
        {
            "p_company_id": COMPANY,
            "p_product_id": PRODUTO_ID,
            "p_kind": "ENTRADA",
            "p_quantity": 12,
            "p_note": "Compra NF 4821",
            "p_confirm": False,
            "p_supplier_id": "supplier-1",
        },
    )


def test_leitura_mostra_fornecedor_da_entrada_historica():
    tables = movimentos_falsos()
    tables["stock_movements"][0]["supplier_id"] = "supplier-1"
    tables["suppliers"] = [
        {"id": "supplier-1", "company_id": COMPANY, "name": "Comercial Sul"}
    ]
    client = ClienteFalso(tables)

    movement = repositorio(client).list_movements()[1]

    assert movement[0] == MOV_ID
    assert movement[8] == "Comercial Sul"
    supplier_queries = [filters for table, filters in client.consultas if table == "suppliers"]
    assert supplier_queries and supplier_queries[0]["company_id"] == COMPANY


def test_nota_vazia_vira_null():
    """`''` faria um filtro por nota preenchida achar movimentação sem nota."""
    cliente = ClienteFalso(
        movimentos_falsos(), rpc_resultados={"fn_register_movement": MOV_ID}
    )
    repositorio(cliente).register(entrada(note="   "))
    assert args_de(cliente, "fn_register_movement")["p_note"] is None


def test_register_de_produto_inexistente_levanta_antes_da_rede():
    cliente = ClienteFalso(movimentos_falsos())
    with pytest.raises(LookupError, match="PRD-404"):
        repositorio(cliente).register(entrada(product_code="PRD-404"))
    assert not cliente.chamadas_rpc


@pytest.mark.parametrize("metodo,funcao", [
    ("confirm", "fn_confirm_movement"),
    ("cancel", "fn_cancel_movement"),
])
def test_confirmar_e_cancelar_nao_mandam_company_id(metodo, funcao):
    """As funções resolvem a empresa pela própria linha.

    Mandar `p_company_id` daqui reabriria o buraco que elas fecham: agir sobre
    movimentação de outra empresa bastando informar uma onde se tem alçada.
    """
    cliente = ClienteFalso(movimentos_falsos())
    getattr(repositorio(cliente), metodo)(MOV_ID)
    assert args_de(cliente, funcao) == {"p_movement_id": MOV_ID}


# ======================================================
# Supabase — permissão
# ======================================================


@pytest.mark.parametrize("erro", [
    ErroDoPostgrest("Sem permissão para movimentar estoque nesta empresa", code="42501"),
    ErroDoPostgrest("permission denied for function fn_register_movement"),
])
def test_recusa_do_banco_vira_erro_de_dominio(erro):
    """A tela só captura `PermissionDeniedError`; crua, viraria traceback."""
    cliente = ClienteFalso(movimentos_falsos(), rpc_erros={"fn_register_movement": erro})

    with pytest.raises(PermissionDeniedError) as capturado:
        repositorio(cliente, role="SELLER").register(entrada())

    # O mesmo rótulo que `MovementService` passa a `ensure_can_move_stock`.
    assert "registrar movimentações" in str(capturado.value)
    assert "SELLER" in str(capturado.value)


def test_movimentacao_de_outra_empresa_tambem_e_recusa():
    """`fn_confirm_movement` responde "não encontrada OU sem permissão".

    A mensagem é única de propósito, para não vazar a existência de linha de
    outra empresa — e por isso precisa ser lida como recusa, não como falha
    desconhecida.
    """
    erro = ErroDoPostgrest("Movimentação não encontrada ou sem permissão", code="42501")
    cliente = ClienteFalso(movimentos_falsos(), rpc_erros={"fn_confirm_movement": erro})

    with pytest.raises(PermissionDeniedError, match="confirmar movimentações"):
        repositorio(cliente).confirm(MOV_ID)


def test_erro_que_nao_e_de_permissao_sobe_como_veio():
    """Quantidade inválida não é falta de permissão, e não pode virar uma."""
    erro = ErroDoPostgrest("Quantidade deve ser maior que zero", code="23514")
    cliente = ClienteFalso(movimentos_falsos(), rpc_erros={"fn_register_movement": erro})

    with pytest.raises(ErroDoPostgrest):
        repositorio(cliente).register(entrada())


# ======================================================
# Demonstração — o saldo
# ======================================================


def test_pendente_nao_mexe_no_saldo():
    """O coração da US03, e no modo demonstração não há trigger para garantir."""
    produtos = catalogo_demo(stock="18")
    repo = DemoMovementRepository(produtos, agora=AGORA)

    repo.register(entrada(quantity=12))

    assert produtos["PRD-009"].stock == "18"


def test_confirmar_move_o_saldo_no_catalogo_compartilhado():
    """É o mesmo dict que as telas leem — essa identidade é o que reflete."""
    produtos = catalogo_demo(stock="18")
    repo = DemoMovementRepository(produtos, agora=AGORA)

    movimento = repo.register(entrada(quantity=12))
    repo.confirm(movimento)

    assert produtos["PRD-009"].stock == "30"


def test_saida_confirmada_subtrai():
    """O sinal vem da espécie, nunca da quantidade (que é sempre positiva)."""
    produtos = catalogo_demo(stock="18")
    repo = DemoMovementRepository(produtos, agora=AGORA)

    repo.register(entrada(kind=MovementKind.SAIDA, quantity=5, confirm=True))

    assert produtos["PRD-009"].stock == "13"


def test_a_situacao_de_estoque_e_recalculada_e_nunca_copiada():
    """Saldo novo com status velho faria a tabela alertar pelo valor anterior.

    Mínimo 10: sair de 18 (Normal) para 6 tem que virar "Baixo" sozinho, pela
    mesma regra de `fn_stock_state`.
    """
    produtos = catalogo_demo(stock="18", minimum_stock=10)
    repo = DemoMovementRepository(produtos, agora=AGORA)

    repo.register(entrada(kind=MovementKind.SAIDA, quantity=12, confirm=True))

    assert produtos["PRD-009"].stock == "6"
    assert produtos["PRD-009"].stock_status == "Baixo"


def test_cancelar_uma_confirmada_devolve_o_saldo():
    produtos = catalogo_demo(stock="18")
    repo = DemoMovementRepository(produtos, agora=AGORA)

    movimento = repo.register(entrada(quantity=12, confirm=True))
    repo.cancel(movimento)

    assert produtos["PRD-009"].stock == "18"


def test_cancelar_uma_pendente_nao_mexe_em_nada():
    produtos = catalogo_demo(stock="18")
    repo = DemoMovementRepository(produtos, agora=AGORA)

    movimento = repo.register(entrada(quantity=12))
    repo.cancel(movimento)

    assert produtos["PRD-009"].stock == "18"


def test_cancelar_duas_vezes_nao_devolve_o_saldo_duas_vezes():
    produtos = catalogo_demo(stock="18")
    repo = DemoMovementRepository(produtos, agora=AGORA)

    movimento = repo.register(entrada(quantity=12, confirm=True))
    repo.cancel(movimento)
    repo.cancel(movimento)

    assert produtos["PRD-009"].stock == "18"


def test_confirmar_duas_vezes_e_recusado():
    """Confirmar de novo aplicaria a diferença duas vezes."""
    produtos = catalogo_demo(stock="18")
    repo = DemoMovementRepository(produtos, agora=AGORA)

    movimento = repo.register(entrada(quantity=12))
    repo.confirm(movimento)

    with pytest.raises(ValueError, match="pendente"):
        repo.confirm(movimento)
    assert produtos["PRD-009"].stock == "30"


def test_saida_sem_saldo_e_recusada_sem_alterar_historico():
    """Espelha CHECK products.stock >= 0, sem truncar saldo nem gravar a saída."""
    produtos = catalogo_demo(stock="2")
    repo = DemoMovementRepository(produtos, agora=AGORA)
    with pytest.raises(ValueError, match="Saldo insuficiente"):
        repo.register(entrada(kind=MovementKind.SAIDA, quantity=5, confirm=True))
    assert produtos["PRD-009"].stock == "2"
    assert repo.list_movements() == ()


# ======================================================
# Demonstração — o histórico
# ======================================================


def test_o_historico_e_proprio_e_vem_do_mais_recente():
    produtos = catalogo_demo()
    repo = DemoMovementRepository(produtos, agora=AGORA)

    repo.register(entrada(quantity=12))
    repo.register(entrada(kind=MovementKind.SAIDA, quantity=3))

    especies = [linha[3] for linha in repo.list_movements()]
    assert especies == ["Saída", "Entrada"]


def test_a_tupla_da_demonstracao_e_a_mesma_do_banco():
    """Trocar a fonte não pode virar refatoração de widget."""
    produtos = catalogo_demo()
    repo = DemoMovementRepository(produtos, agora=AGORA)
    movimento = repo.register(entrada(quantity=12))

    assert repo.list_movements() == ((
        movimento,
        "PRD-009",
        'Monitor LG UltraWide 34"',
        "Entrada",
        12,
        "Pendente",
        "Compra NF 4821",
        "Hoje, 18:30",
        VAZIO,
        VAZIO,
    ),)


def test_filtro_por_produto_no_historico():
    produtos = catalogo_demo()
    produtos["PRD-008"] = Product('PRD-008', 'Teclado', 'Periféricos',
                                  'Unidade (UN)', 'R$ 459,90', 'R$ 280,00',
                                  True, '6', 'Baixo', minimum_stock=10)
    repo = DemoMovementRepository(produtos, agora=AGORA)
    repo.register(entrada(quantity=12))
    repo.register(entrada(product_code="PRD-008", quantity=4))

    assert [linha[1] for linha in repo.list_movements("PRD-009")] == ["PRD-009"]


def test_registrar_para_produto_inexistente_levanta():
    """Espelha o `foreign_key_violation` de `fn_register_movement`."""
    repo = DemoMovementRepository(catalogo_demo(), agora=AGORA)
    with pytest.raises(LookupError, match="PRD-404"):
        repo.register(entrada(product_code="PRD-404"))


def test_confirmar_id_inexistente_levanta():
    repo = DemoMovementRepository(catalogo_demo(), agora=AGORA)
    with pytest.raises(LookupError, match="MOV-404"):
        repo.confirm("MOV-404")


def test_ids_nao_sao_reaproveitados():
    """Id reaproveitado faria confirmar uma confirmar a outra."""
    repo = DemoMovementRepository(catalogo_demo(), agora=AGORA)
    primeiro = repo.register(entrada())
    segundo = repo.register(entrada())
    assert primeiro != segundo and segundo > primeiro


def test_a_situacao_registrada_segue_o_enum_do_dominio():
    """Sem isso, a tradução de rótulo esconderia um valor fora do enum."""
    repo = DemoMovementRepository(catalogo_demo(), agora=AGORA)
    repo.register(entrada())
    repo.register(entrada(confirm=True))

    situacoes = [linha[5] for linha in repo.list_movements()]
    assert situacoes == [MovementStatus.CONFIRMADA.label, MovementStatus.PENDENTE.label]


# -------------------------------------------------------- tupla de 10 campos
# A cauda da tupla era OPCIONAL: o fornecedor só era acrescentado quando
# existia, e a tela lia `mov[8] if len(mov) > 8`. Pendurar o motivo do ajuste
# nisso colocaria "Quebra / avaria" na coluna Fornecedor toda vez que o
# produto não tivesse fornecedor — a maioria das saídas.

CAMPOS = 10
I_FORNECEDOR, I_MOTIVO = 8, 9


def test_movimentacao_sem_fornecedor_ainda_tem_dez_campos():
    repo = DemoMovementRepository(
        {"P1": Product("P1", "Arroz", "Grãos", "UN", "10,00", "5,00", True, "42", "Normal")},
        agora=AGORA,
    )
    repo.register(MovementInput("P1", MovementKind.SAIDA, 2, confirm=True))

    linha = repo.list_movements()[0]

    assert len(linha) == CAMPOS
    assert linha[I_FORNECEDOR] == VAZIO
    assert linha[I_MOTIVO] == VAZIO


def test_o_fornecedor_nao_escorrega_para_a_coluna_do_motivo():
    """Posição fixa: fornecedor é sempre 8, motivo é sempre 9."""
    tabelas = movimentos_falsos()
    repo = SupabaseMovementRepository(ClienteFalso(tabelas), COMPANY, agora=AGORA)

    for linha in repo.list_movements():
        assert len(linha) == CAMPOS


# ------------------------------------------------------------- ajuste (H11)
# Do adaptador de demonstração o que se prova é mais forte que do de banco,
# porque ele É a implementação: aqui não há trigger nem transação, então a
# atomicidade e o saldo resultante precisam ser código testado.

from stockflow.application.dto.adjustment_input import AdjustmentInput
from stockflow.domain.enums.adjustment_reason import AdjustmentReason
from stockflow.domain.exceptions.adjustment_errors import (
    AjusteSemEfeitoError,
    SaldoDesatualizadoError,
)


def catalogo_de_um(stock="42", active=True):
    return {"P1": Product("P1", "Arroz", "Grãos", "UN", "10,00", "5,00",
                          active, stock, "Normal")}


def ajuste(**kwargs):
    base = dict(product_code="P1", counted_balance=38, expected_balance=42,
                reason=AdjustmentReason.QUEBRA, detail="")
    base.update(kwargs)
    return AdjustmentInput(**base)


def test_ajuste_leva_o_saldo_exatamente_ao_contado():
    produtos = catalogo_de_um("42")
    repo = DemoMovementRepository(produtos, agora=AGORA)

    repo.adjust(ajuste(counted_balance=38))

    assert produtos["P1"].stock == "38"


def test_contar_mais_do_que_havia_vira_entrada():
    produtos = catalogo_de_um("42")
    repo = DemoMovementRepository(produtos, agora=AGORA)

    repo.adjust(ajuste(counted_balance=50, reason=AdjustmentReason.CONTAGEM))

    assert produtos["P1"].stock == "50"
    assert repo.list_movements()[0][3] == MovementKind.ENTRADA.label


def test_o_ajuste_nasce_confirmado_e_carrega_o_motivo():
    """Não há par registrar/confirmar: a contagem vale no ato."""
    produtos = catalogo_de_um("42")
    repo = DemoMovementRepository(produtos, agora=AGORA)

    repo.adjust(ajuste(counted_balance=38))
    linha = repo.list_movements()[0]

    assert linha[5] == MovementStatus.CONFIRMADA.label
    assert linha[9] == AdjustmentReason.QUEBRA.label


def test_saldo_mudou_desde_a_contagem_e_recusado_sem_gravar():
    produtos = catalogo_de_um("45")   # alguém movimentou; a tela viu 42
    repo = DemoMovementRepository(produtos, agora=AGORA)

    with pytest.raises(SaldoDesatualizadoError):
        repo.adjust(ajuste(expected_balance=42, counted_balance=38))

    assert produtos["P1"].stock == "45", "o saldo foi alterado apesar da recusa"
    assert repo.list_movements() == ()


def test_produto_inativo_nao_e_ajustado():
    produtos = catalogo_de_um("42", active=False)
    repo = DemoMovementRepository(produtos, agora=AGORA)

    with pytest.raises(ValueError):
        repo.adjust(ajuste())

    # Literal "42", não uma variável capturada antes da chamada: comparar o
    # saldo com ele mesmo depois do `adjust` não provaria nada se o código
    # tivesse mutado o MESMO objeto.
    assert produtos["P1"].stock == "42", "o saldo foi alterado apesar da recusa"
    assert repo.list_movements() == ()


def test_outro_sem_detalhe_e_recusado_como_no_banco():
    """Espelha `ck_movements_adjustment_detail`.

    Sem isto, o modo demonstração aceitaria o que o Postgres recusa, e o bug
    só apareceria para quem roda com banco.
    """
    produtos = catalogo_de_um("42")
    repo = DemoMovementRepository(produtos, agora=AGORA)

    with pytest.raises(ValueError):
        repo.adjust(ajuste(reason=AdjustmentReason.OUTRO, detail=""))

    assert produtos["P1"].stock == "42", "o saldo foi alterado apesar da recusa"
    assert repo.list_movements() == ()


def test_zerar_o_saldo_e_ajuste_valido():
    produtos = catalogo_de_um("5")
    repo = DemoMovementRepository(produtos, agora=AGORA)

    repo.adjust(ajuste(counted_balance=0, expected_balance=5,
                       reason=AdjustmentReason.PERDA))

    assert produtos["P1"].stock == "0"


def test_contado_igual_ao_atual_e_ajuste_sem_efeito():
    """Espelha o `IF p_counted_balance = v_current` do banco.

    É a recusa NOMEADA (`AjusteSemEfeitoError`), não qualquer `ValueError`:
    a tela usa esse nome para desabilitar o botão antes do clique, e um
    `ValueError` genérico esconderia essa distinção.
    """
    produtos = catalogo_de_um("42")
    repo = DemoMovementRepository(produtos, agora=AGORA)

    with pytest.raises(AjusteSemEfeitoError):
        repo.adjust(ajuste(counted_balance=42, expected_balance=42))

    assert produtos["P1"].stock == "42", "o saldo foi alterado apesar da recusa"
    assert repo.list_movements() == ()


def test_contado_negativo_e_recusado_sem_gravar():
    """Espelha o guard `p_counted_balance IS NULL OR p_counted_balance < 0`."""
    produtos = catalogo_de_um("42")
    repo = DemoMovementRepository(produtos, agora=AGORA)

    with pytest.raises(ValueError):
        repo.adjust(ajuste(counted_balance=-1, expected_balance=42))

    assert produtos["P1"].stock == "42", "o saldo foi alterado apesar da recusa"
    assert repo.list_movements() == ()


def test_a_ordem_das_recusas_espelha_a_funcao_sql():
    """Produto inativo E `OUTRO` sem detalhe ao mesmo tempo.

    `fn_register_adjustment` confere o motivo ANTES de travar a linha do
    produto; se o adaptador de demonstração invertesse essa ordem, a mesma
    entrada errada produziria uma mensagem diferente contra o banco e contra
    a demonstração — e é exatamente essa divergência que pinça este teste.
    """
    produtos = catalogo_de_um("42", active=False)
    repo = DemoMovementRepository(produtos, agora=AGORA)

    with pytest.raises(ValueError, match="Outro"):
        repo.adjust(ajuste(reason=AdjustmentReason.OUTRO, detail=""))

    # É justamente aqui, com DUAS condições erradas ao mesmo tempo, que um
    # estado pela metade apareceria primeiro: saldo E status literais da
    # fixture, não recalculados a partir de um saldo fantasma.
    assert produtos["P1"].stock == "42", "o saldo foi alterado apesar da recusa"
    assert produtos["P1"].stock_status == "Normal", "o status foi recalculado apesar da recusa"
    assert repo.list_movements() == ()

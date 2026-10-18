"""O serviço de ajuste recusa antes de tocar no repositório (H11).

A ordem importa e é a mesma do `ProductService`: permissão primeiro, inclusive
antes de leitura. Um papel sem alçada não pode nem descobrir, pela mensagem de
erro, se o produto existe.
"""

import pytest

from stockflow.application.dto.adjustment_input import AdjustmentInput
from stockflow.application.services.movement_service import MovementService
from stockflow.domain.enums.adjustment_reason import AdjustmentReason
from stockflow.domain.enums.user_role import UserRole
from stockflow.domain.exceptions.permission_denied import PermissionDeniedError
from stockflow.presentation.demo_products import Product


class RepositorioEspiao:
    """Registra o que foi chamado. Qualquer chamada é falha num teste de recusa."""

    def __init__(self):
        self.chamadas = []

    def adjust(self, data):
        self.chamadas.append(data)
        return "MOV-001"


class CatalogoFalso:
    """Catálogo que CONTA as consultas.

    Contar é o que torna a ordem das recusas observável. Sem isto, "o motivo
    é conferido antes do produto" só se verifica lendo o código — e foi
    exatamente assim que o serviço passou a divergir de `fn_register_adjustment`
    sem nenhum teste ficar vermelho.
    """

    def __init__(self, produtos):
        self._produtos = produtos
        self.consultas = []

    def get(self, code):
        self.consultas.append(code)
        return self._produtos.get(code)


class SessaoFalsa:
    def __init__(self, role):
        self.role = role


def produto(code="P1", active=True, stock="42"):
    return Product(code, "Arroz", "Grãos", "UN", "10,00", "5,00", active, stock, "Normal")


def servico(produtos=None):
    repo = RepositorioEspiao()
    catalogo = CatalogoFalso(produtos if produtos is not None else {"P1": produto()})
    return MovementService(repo, product_repository=catalogo), repo


def pedido(**kwargs):
    base = dict(
        product_code="P1", counted_balance=38, expected_balance=42,
        reason=AdjustmentReason.QUEBRA, detail="",
    )
    base.update(kwargs)
    return AdjustmentInput(**base)


def test_vendedor_e_recusado_sem_tocar_no_repositorio(seller_session):
    service, repo = servico()

    with pytest.raises(PermissionDeniedError):
        service.adjust(SessaoFalsa(UserRole.SELLER), pedido())

    assert repo.chamadas == [], "o repositório foi chamado apesar da recusa"


def test_sessao_ausente_e_recusada():
    service, repo = servico()

    with pytest.raises(PermissionDeniedError):
        service.adjust(None, pedido())

    assert repo.chamadas == []


@pytest.mark.parametrize("papel", [UserRole.ADMIN, UserRole.STOCK])
def test_admin_e_estoquista_ajustam(papel):
    service, repo = servico()

    assert service.adjust(SessaoFalsa(papel), pedido()) == "MOV-001"
    assert len(repo.chamadas) == 1


def test_motivo_outro_sem_detalhe_e_recusado_antes_da_rede():
    service, repo = servico()

    with pytest.raises(ValueError, match="Outro"):
        service.adjust(
            SessaoFalsa(UserRole.STOCK),
            pedido(reason=AdjustmentReason.OUTRO, detail="   "),
        )

    assert repo.chamadas == []


def test_motivo_outro_com_detalhe_passa():
    service, repo = servico()

    service.adjust(
        SessaoFalsa(UserRole.STOCK),
        pedido(reason=AdjustmentReason.OUTRO, detail="Caixa amassada na doca"),
    )

    assert len(repo.chamadas) == 1


def test_produto_inativo_e_recusado():
    service, repo = servico({"P1": produto(active=False)})

    with pytest.raises(ValueError, match="ativo"):
        service.adjust(SessaoFalsa(UserRole.STOCK), pedido())

    assert repo.chamadas == []


def test_contado_negativo_e_recusado():
    service, repo = servico()

    with pytest.raises(ValueError):
        service.adjust(SessaoFalsa(UserRole.STOCK), pedido(counted_balance=-1))

    assert repo.chamadas == []


def test_sem_diferenca_nao_vira_requisicao():
    """Contado igual ao exibido: a recusa é local, não um erro do Postgres."""
    service, repo = servico()

    with pytest.raises(ValueError):
        service.adjust(
            SessaoFalsa(UserRole.STOCK),
            pedido(counted_balance=42, expected_balance=42),
        )

    assert repo.chamadas == []


# --------------------------------------- o saldo contado não ganha um padrão


def test_contar_zero_sem_saldo_exibido_e_ajuste_valido():
    """`expected_balance=None` é o opt-out da checagem de concorrência.

    A função SQL o documenta (`IF p_expected_balance IS NOT NULL AND ...`) e
    os dois adaptadores o respeitam. O serviço convertia o `None` para zero
    antes de comparar, então uma contagem legítima de zero batia com o
    "esperado" fabricado e era recusada como ajuste sem efeito — justamente
    na camada por onde toda chamada real passa.
    """
    service, repo = servico()

    assert service.adjust(
        SessaoFalsa(UserRole.STOCK),
        pedido(counted_balance=0, expected_balance=None),
    ) == "MOV-001"
    assert len(repo.chamadas) == 1


def test_sem_saldo_exibido_o_contado_negativo_continua_recusado():
    """Pular a checagem de concorrência não é pular a validação do contado."""
    service, repo = servico()

    with pytest.raises(ValueError, match="negativo"):
        service.adjust(
            SessaoFalsa(UserRole.STOCK),
            pedido(counted_balance=-1, expected_balance=None),
        )

    assert repo.chamadas == []


@pytest.mark.parametrize("contado", [None, "", "   ", "trinta", "38,5"])
def test_contado_ilegivel_recusa_em_vez_de_virar_zero(contado):
    """Zero não é um padrão aceitável para o número que decide quanto sai.

    `to_int` devolve zero em valor ilegível, e isso é certo para uma
    LISTAGEM — uma célula ruim não derruba a tabela. Aqui seria a ordem
    silenciosa de esvaziar o produto: `0` é uma contagem válida.
    """
    service, repo = servico()

    with pytest.raises(ValueError):
        service.adjust(SessaoFalsa(UserRole.STOCK), pedido(counted_balance=contado))

    assert repo.chamadas == [], "um contado ilegível chegou ao repositório"


# ------------------------- a ordem das recusas espelha fn_register_adjustment


def test_o_motivo_e_conferido_antes_de_consultar_o_produto():
    """Produto inativo E `OUTRO` sem detalhe ao mesmo tempo.

    `fn_register_adjustment` confere o motivo ANTES de travar a linha do
    produto, e o adaptador de demonstração espelha essa ordem. Com a ordem
    invertida aqui, a mesma entrada errada recebia "Selecione um produto
    ativo." pelo serviço e a mensagem da justificativa pelo banco.
    """
    repo = RepositorioEspiao()
    catalogo = CatalogoFalso({"P1": produto(active=False)})
    service = MovementService(repo, product_repository=catalogo)

    with pytest.raises(ValueError, match="Outro"):
        service.adjust(
            SessaoFalsa(UserRole.STOCK),
            pedido(reason=AdjustmentReason.OUTRO, detail=""),
        )

    assert catalogo.consultas == [], "o produto foi consultado antes de conferir o motivo"
    assert repo.chamadas == []


def test_o_contado_e_conferido_antes_de_consultar_o_produto():
    """Primeiro guard da função SQL: contado nulo ou negativo.

    Ele roda antes até do `SELECT ... FOR UPDATE`, porque um contado inválido
    é erro de entrada e não depende de qual produto foi escolhido.
    """
    repo = RepositorioEspiao()
    catalogo = CatalogoFalso({"P1": produto()})
    service = MovementService(repo, product_repository=catalogo)

    with pytest.raises(ValueError, match="negativo"):
        service.adjust(SessaoFalsa(UserRole.STOCK), pedido(counted_balance=-1))

    assert catalogo.consultas == [], "o produto foi consultado antes de conferir o contado"
    assert repo.chamadas == []

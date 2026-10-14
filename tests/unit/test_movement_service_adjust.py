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
    def __init__(self, produtos):
        self._produtos = produtos

    def get(self, code):
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


def test_vendedor_e_recusado_sem_tocar_no_repositorio():
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

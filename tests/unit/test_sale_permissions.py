"""A guarda de permissão roda ANTES de tocar o repositório (US17).

Padrão aprovado neste projeto: o fluxo negado não pode vazar informação nem
gastar consulta. O espião prova que o repositório não foi chamado — sem ele,
um serviço que consulta primeiro e recusa depois passaria igual.
"""

import pytest

from stockflow.application.dto.sale_filter import SaleFilter, SalePage
from stockflow.application.services.sale_service import SaleService
from stockflow.domain.enums.user_role import UserRole
from stockflow.domain.exceptions.permission_denied import PermissionDeniedError
from stockflow.presentation.demo_accounts import conta_por_papel


class RepositorioEspiao:
    def __init__(self):
        self.chamadas = []

    def list_page(self, filtro, page, size):
        self.chamadas.append("list_page")
        return SalePage(rows=(), total=0, page=page, size=size)

    def get(self, sale_id):
        self.chamadas.append("get")
        return {"id": sale_id}

    def cancel(self, sale_id, reason):
        self.chamadas.append("cancel")
        return {"sale_id": sale_id, "reason": reason}

    def revert(self, sale_id, reason):
        self.chamadas.append("revert")
        return {"sale_id": sale_id, "reason": reason}


def servico():
    repositorio = RepositorioEspiao()
    return SaleService(repositorio, clients=None, products=None), repositorio


def sessao(papel):
    return conta_por_papel(papel).session()


@pytest.mark.parametrize("papel", [UserRole.STOCK, UserRole.SELLER])
def test_reverter_sem_alcada_nao_toca_o_repositorio(papel):
    service, repositorio = servico()
    with pytest.raises(PermissionDeniedError):
        service.cancel_sale(sessao(papel), "venda-1", "engano")
    with pytest.raises(PermissionDeniedError):
        service.return_sale(sessao(papel), "venda-1", "cliente devolveu")
    assert repositorio.chamadas == []


def test_sessao_ausente_nao_reverte():
    service, repositorio = servico()
    with pytest.raises(PermissionDeniedError):
        service.cancel_sale(None, "venda-1", "engano")
    assert repositorio.chamadas == []


def test_admin_reverte():
    service, repositorio = servico()
    service.cancel_sale(sessao(UserRole.ADMIN), "venda-1", "engano")
    service.return_sale(sessao(UserRole.ADMIN), "venda-1", "devolvido")
    assert repositorio.chamadas == ["cancel", "revert"]


@pytest.mark.parametrize("motivo", ["", "   ", None])
def test_motivo_vazio_e_recusado_antes_do_repositorio(motivo):
    """Validação de domínio não gasta ida ao banco.

    O banco recusa vazio também; deixar a recusa só lá custaria uma ida à
    rede para dizer o que a aplicação já sabia.
    """
    service, repositorio = servico()
    with pytest.raises(ValueError, match="motivo"):
        service.cancel_sale(sessao(UserRole.ADMIN), "venda-1", motivo)
    assert repositorio.chamadas == []


def test_motivo_longo_demais_e_recusado():
    service, repositorio = servico()
    with pytest.raises(ValueError):
        service.cancel_sale(sessao(UserRole.ADMIN), "venda-1", "x" * 301)
    assert repositorio.chamadas == []


def test_motivo_chega_ao_repositorio_sem_espaco_em_volta():
    service, repositorio = servico()
    gravado = service.cancel_sale(sessao(UserRole.ADMIN), "venda-1", "  engano  ")
    assert gravado["reason"] == "engano"


def test_consulta_exige_sessao_com_alcada_de_leitura():
    service, repositorio = servico()
    with pytest.raises(PermissionDeniedError):
        service.list_sales(None)
    assert repositorio.chamadas == []


@pytest.mark.parametrize("papel", [UserRole.ADMIN, UserRole.STOCK, UserRole.SELLER])
def test_os_tres_papeis_consultam_o_historico(papel):
    service, repositorio = servico()
    service.list_sales(sessao(papel))
    assert repositorio.chamadas == ["list_page"]


def test_detalhe_tambem_exige_alcada_de_leitura():
    service, repositorio = servico()
    with pytest.raises(PermissionDeniedError):
        service.get_sale(None, "venda-1")
    assert repositorio.chamadas == []


def test_filtro_vazio_e_o_padrao_e_nao_exige_construcao():
    service, _ = servico()
    assert isinstance(service.list_sales(sessao(UserRole.ADMIN)), SalePage)


@pytest.mark.parametrize("tamanho", [0, -1, 500])
def test_tamanho_de_pagina_fora_do_limite_e_recusado(tamanho):
    service, repositorio = servico()
    with pytest.raises(ValueError):
        service.list_sales(sessao(UserRole.ADMIN), size=tamanho)
    assert repositorio.chamadas == []


@pytest.mark.parametrize("numero", [0, -3])
def test_pagina_invalida_e_recusada(numero):
    service, repositorio = servico()
    with pytest.raises(ValueError):
        service.list_sales(sessao(UserRole.ADMIN), page=numero)
    assert repositorio.chamadas == []


def test_pagina_calcula_quantas_paginas_existem():
    pagina = SalePage(rows=(), total=101, page=1, size=50)
    assert pagina.pages == 3
    assert pagina.has_next
    assert not pagina.has_previous


def test_pagina_sem_linhas_tem_uma_pagina():
    """Zero resultado continua sendo "página 1 de 1", não "de 0"."""
    assert SalePage(rows=(), total=0, page=1, size=50).pages == 1


def test_ultima_pagina_nao_oferece_proxima():
    pagina = SalePage(rows=(), total=100, page=2, size=50)
    assert not pagina.has_next
    assert pagina.has_previous


def test_filtro_recusa_ordenacao_desconhecida():
    """Lista fechada: o banco recusa igual, mas a tela não deve nem tentar."""
    with pytest.raises(ValueError):
        SaleFilter(sort="id; DROP TABLE sales")


def test_filtro_recusa_periodo_invertido():
    from datetime import date

    with pytest.raises(ValueError):
        SaleFilter(date_from=date(2026, 10, 10), date_to=date(2026, 10, 1))


def test_filtro_sabe_se_esta_ativo():
    assert not SaleFilter().ativo
    assert SaleFilter(client_id="c1").ativo


def test_filtro_troca_campo_sem_remontar():
    filtro = SaleFilter(client_id="c1")
    assert filtro.com(status="CANCELADA").client_id == "c1"
    assert filtro.com(status="CANCELADA").status == "CANCELADA"

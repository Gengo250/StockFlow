"""US08: cadastro, pesquisa, status e integração de fornecedores."""

import pytest

from stockflow.application.dto.supplier_input import SupplierInput
from stockflow.application.dto.movement_input import MovementInput
from stockflow.application.dto.product_input import ProductInput
from stockflow.application.services.supplier_service import SupplierService
from stockflow.domain.enums.movement_kind import MovementKind
from stockflow.domain.enums.user_role import UserRole
from stockflow.domain.permissions import can_manage_suppliers
from stockflow.domain.exceptions.permission_denied import PermissionDeniedError
from stockflow.infrastructure.repositories.demo_supplier_repository import (
    DemoSupplierRepository,
)
from stockflow.presentation.demo_accounts import conta_por_papel
from stockflow.presentation.windows.main_window import MainWindow
from PySide6.QtWidgets import QMessageBox


CPF = "529.982.247-25"


@pytest.fixture
def fornecedores():
    repository = DemoSupplierRepository({})
    return repository, SupplierService(repository)


@pytest.fixture
def admin():
    return conta_por_papel(UserRole.ADMIN).session()


def test_create_edit_documento_opcional_e_soft_delete(fornecedores, admin):
    repository, service = fornecedores
    supplier = service.create_supplier(
        admin,
        SupplierInput(
            name="Distribuidora Sul", document=CPF, phone="(11) 99887-7665",
            email="sul@example.com", address="Rua Central, 15",
        ),
    )
    assert supplier.document == "52998224725"
    assert service.get_supplier(admin, supplier.supplier_id).address == "Rua Central, 15"

    updated = service.update_supplier(
        admin,
        supplier.supplier_id,
        SupplierInput(
            name="Distribuidora Sul LTDA", document=CPF,
            phone="11988776655", email="novo@example.com", address="Novo endereço",
            active=True,
        ),
    )
    assert updated.document == supplier.document
    assert updated.email == "novo@example.com"

    inactive = service.set_active(admin, supplier.supplier_id, False)
    assert inactive.status == "Inativo"
    assert repository.get(supplier.supplier_id) is inactive
    assert supplier not in repository.list_active()

    without_document = service.create_supplier(
        admin, SupplierInput(name="Fornecedor sem documento")
    )
    assert without_document.document == ""


@pytest.mark.parametrize("document", ["123", "52998224724", "11111111111", "abc"])
def test_cpf_cnpj_invalido_recusado(fornecedores, admin, document):
    _, service = fornecedores
    with pytest.raises(ValueError, match="CPF/CNPJ"):
        service.create_supplier(
            admin, SupplierInput(name="Documento inválido", document=document)
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"email": "sem-arroba"},
        {"email": "a@b"},
        {"phone": "1234"},
        {"phone": "telefone"},
    ],
)
def test_contatos_opcionais_sao_validados(fornecedores, admin, overrides):
    _, service = fornecedores
    with pytest.raises(ValueError):
        service.create_supplier(
            admin, SupplierInput(name="Contato inválido", **overrides)
        )


def test_nome_obrigatorio(fornecedores, admin):
    _, service = fornecedores
    with pytest.raises(ValueError, match="Nome ou razão social"):
        service.create_supplier(admin, SupplierInput(name=" "))


def test_documento_duplicado_inativo_tambem_e_recusado(fornecedores, admin):
    _, service = fornecedores
    first = service.create_supplier(
        admin, SupplierInput(name="Primeiro", document=CPF)
    )
    service.set_active(admin, first.supplier_id, False)
    with pytest.raises(ValueError, match="Já existe"):
        service.create_supplier(
            admin, SupplierInput(name="Duplicado", document="52998224725")
        )


def test_editar_o_proprio_documento_nao_gera_falsa_duplicidade(fornecedores, admin):
    _, service = fornecedores
    first = service.create_supplier(
        admin, SupplierInput(name="Original", document=CPF)
    )
    edited = service.update_supplier(
        admin, first.supplier_id,
        SupplierInput(name="Editado", document="52998224725"),
    )
    assert edited.name == "Editado"


def test_edicao_recusa_documento_de_outro_fornecedor(fornecedores, admin):
    _, service = fornecedores
    service.create_supplier(admin, SupplierInput(name="Primeiro", document=CPF))
    second = service.create_supplier(admin, SupplierInput(name="Segundo"))
    with pytest.raises(ValueError, match="Já existe"):
        service.update_supplier(
            admin, second.supplier_id,
            SupplierInput(name="Segundo", document=CPF),
        )


def test_vinculo_de_produto_principal_preservado_apos_inativacao(janela):
    supplier = janela.supplier_repository.list_active()[0]
    product_data = ProductInput(
        code="PRD-010",
        name="Produto de teste",
        category="Eletrônicos",
        unit="Unidade (UN)",
        sale_price="R$ 20,00",
        cost="R$ 10,00",
        stock="0",
        supplier_id=supplier.supplier_id,
    )
    janela.product_service.create_product(janela.session, product_data)
    assert janela.products["PRD-010"].supplier_id == supplier.supplier_id

    janela.supplier_service.set_active(
        janela.session, supplier.supplier_id, False
    )
    janela._show_edit_product(janela.products["PRD-010"])
    assert supplier.name in janela.editar_produto_page.supplier_input.currentText()
    assert "inativo" in janela.editar_produto_page.supplier_input.currentText().casefold()
    edited = ProductInput(
        code="PRD-010",
        name="Produto atualizado",
        category="Eletrônicos",
        unit="Unidade (UN)",
        sale_price="R$ 20,00",
        cost="R$ 10,00",
        stock="0",
        supplier_id=supplier.supplier_id,
    )
    janela.product_service.update_product(
        janela.session, "PRD-010", edited
    )
    assert janela.products["PRD-010"].supplier_id == supplier.supplier_id


def test_busca_por_nome_documento_telefone_email_endereco(fornecedores, admin):
    _, service = fornecedores
    supplier = service.create_supplier(
        admin,
        SupplierInput(
            name="Comercial Horizonte", document=CPF, phone="(11) 99887-7665",
            email="vendas@horizonte.example", address="Av. Brasil 100",
        ),
    )
    for query in ("Horizonte", "529982247", "998877665", "vendas@horizonte", "Brasil"):
        assert [item.supplier_id for item in service.search_suppliers(admin, query)] == [
            supplier.supplier_id
        ]
    assert service.search_suppliers(admin, "sem resultado") == ()


def test_papeis_autorizados_sao_admin_e_stock():
    assert can_manage_suppliers(UserRole.ADMIN)
    assert can_manage_suppliers(UserRole.STOCK)
    assert not can_manage_suppliers(UserRole.SELLER)


def test_sem_permissao_nao_consulta_repositorio():
    class RepositorySpy(DemoSupplierRepository):
        called = False

        def list_all(self):
            self.called = True
            return super().list_all()

    repository = RepositorySpy({})
    service = SupplierService(repository)
    with pytest.raises(PermissionDeniedError):
        service.list_suppliers(conta_por_papel(UserRole.SELLER).session())
    assert not repository.called


@pytest.fixture
def janela(qapp, request):
    window = MainWindow(conta_por_papel(UserRole.ADMIN).session())
    request.addfinalizer(window.close)
    return window


def test_navegacao_fornecedores_e_status_visivel(janela):
    assert janela.sidebar.item_is_visible("fornecedores")
    assert janela.show_page("fornecedores")
    assert janela.pages.currentWidget() is janela.suppliers_page
    assert janela.suppliers_page.table.rowCount() == 2
    assert janela.suppliers_page.table.horizontalHeaderItem(4).text() == "Endereço"
    assert janela.suppliers_page.table_card.objectName() == "suppliersTableCard"
    assert janela.suppliers_page.new_supplier_button.objectName() == "primaryButton"
    assert janela.suppliers_page.table.cellWidget(0, 5).objectName() == "statusBadge"


def test_vendedor_nao_pode_abrir_fornecedores(qapp, monkeypatch, request):
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *args: None))
    window = MainWindow(conta_por_papel(UserRole.SELLER).session())
    request.addfinalizer(window.close)

    assert not window.sidebar.item_is_visible("fornecedores")
    assert window.show_page("fornecedores") is False


def test_busca_da_tela_considera_endereco_e_contato(janela):
    page = janela.suppliers_page
    for query in ("Central", "contato@central", "33334444", "São Paulo"):
        page.search_input.setText(query)
        assert not page.table.isRowHidden(0)
        assert page.table.isRowHidden(1)


def test_seletores_so_oferecem_fornecedores_ativos(janela):
    page = janela.movimentacoes_page
    assert page.fornecedor_combo.count() == 2
    assert page.fornecedor_combo.findData("FOR-002") == -1

    inactive = janela.supplier_repository.get("FOR-002")
    janela.supplier_service.set_active(janela.session, inactive.supplier_id, True)
    janela._refresh_supplier_options()

    assert page.fornecedor_combo.findData("FOR-002") >= 0
    assert janela.novo_produto_page.supplier_input.findData("FOR-002") >= 0


def test_entrada_exige_fornecedor_e_historico_preserva_nome(janela):
    page = janela.movimentacoes_page
    page.produto_combo.setCurrentIndex(page.produto_combo.findData("PRD-009"))
    page.especie_combo.setCurrentIndex(page.especie_combo.findData(MovementKind.ENTRADA))
    page.fornecedor_combo.setCurrentIndex(0)
    page.registrar_confirmar_button.click()
    assert "fornecedor ativo" in page.warning_label.text().casefold()
    assert page.table.rowCount() == 0

    supplier = janela.supplier_repository.list_active()[0]
    page.fornecedor_combo.setCurrentIndex(
        page.fornecedor_combo.findData(supplier.supplier_id)
    )
    page.registrar_confirmar_button.click()
    assert page.table.rowCount() == 1
    assert page.table.item(0, 6).text() == supplier.name
    assert janela.products["PRD-009"].stock == "19"


def test_inativar_fornecedor_preserva_nome_na_compra_existente(janela):
    supplier = janela.supplier_repository.list_active()[0]
    movement = janela.movement_repository.register(
        MovementInput(
            product_code="PRD-009", kind=MovementKind.ENTRADA, quantity=2,
            supplier_id=supplier.supplier_id,
        )
    )
    janela.supplier_service.set_active(
        janela.session, supplier.supplier_id, False
    )
    record = janela.movement_repository.list_movements()[0]
    assert record[0] == movement
    assert record[8] == supplier.name
    assert supplier.supplier_id not in {
        active.supplier_id for active in janela.supplier_repository.list_active()
    }


def test_nova_entrada_recusa_fornecedor_inativo(janela):
    supplier = janela.supplier_repository.list_active()[0]
    janela.supplier_service.set_active(
        janela.session, supplier.supplier_id, False
    )
    with pytest.raises(ValueError, match="fornecedor ativo"):
        janela.movement_service.register(
            janela.session,
            MovementInput(
                product_code="PRD-009", kind=MovementKind.ENTRADA, quantity=1,
                supplier_id=supplier.supplier_id,
            ),
        )

import pytest

from stockflow.domain.enums.user_role import UserRole
from stockflow.domain.exceptions.permission_denied import PermissionDeniedError
from stockflow.infrastructure.repositories.demo_client_repository import DemoClientRepository
from stockflow.infrastructure.repositories.demo_movement_repository import DemoMovementRepository
from stockflow.infrastructure.repositories.demo_sale_repository import DemoSaleRepository
from stockflow.presentation.demo_products import DEMO_PRODUCTS
from stockflow.presentation.demo_scenario import populate_demo_operations
from stockflow.presentation.demo_accounts import conta_por_papel


@pytest.mark.parametrize(
    "role", [UserRole.ADMIN, UserRole.STOCK, UserRole.SELLER]
)
def test_scenario_is_loaded_without_changing_the_operational_session(role):
    session = conta_por_papel(role).session()
    initial_products = dict(DEMO_PRODUCTS)
    products = dict(initial_products)
    movements = DemoMovementRepository(products)
    sales = DemoSaleRepository(products, movements, session=session)

    populate_demo_operations(products, DemoClientRepository(), sales, movements)

    assert sales._session is session
    assert sales._session.role is role
    assert sales._session.company_id == session.company_id
    assert movements.products is products
    assert sales._products is products
    assert {
        code: product.stock for code, product in products.items()
    } == {
        code: product.stock for code, product in initial_products.items()
    }

    sale = next(
        row for row in sales.rows
        if row.get("company_id") == session.company_id
        and row.get("status") == "CONCLUIDA"
    )
    if role is not UserRole.ADMIN:
        for reverse in (sales.cancel, sales.revert):
            with pytest.raises(PermissionDeniedError):
                reverse(sale["id"], "teste de permissão")
        assert sale["status"] == "CONCLUIDA"

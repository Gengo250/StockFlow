from copy import deepcopy
from decimal import Decimal

import pytest

from stockflow.domain.sale_return import CalculatedReturnItem
from stockflow.infrastructure.repositories.demo_movement_repository import DemoMovementRepository
from stockflow.presentation.demo_products import Product

SALE = "00000000-0000-0000-0000-000000000001"
RETURN = "00000000-0000-0000-0000-000000000002"
ITEM = "00000000-0000-0000-0000-000000000003"
ITEM2 = "00000000-0000-0000-0000-000000000004"


def line(item=ITEM, quantity=1):
    return CalculatedReturnItem(item, "P1", quantity, Decimal("1"), Decimal("0"), Decimal(quantity))


def repository(*, maximum=None, company_max=None, active=True):
    products = {"P1": Product("P1", "Produto", "Categoria", "UN", "1", "0", active,
                              "4", "Normal", minimum_stock=5, maximum_stock=maximum)}
    return DemoMovementRepository(products, company_max_stock_limit=company_max), products


def register(repo, items, **kwargs):
    return repo.register_return(RETURN, SALE, items, created_by="admin", company_id="company", **kwargs)


def test_confirmed_entry_updates_stock_status_even_if_product_inactive():
    repo, products = repository(active=False)
    ids = register(repo, (line(quantity=3),))
    assert products["P1"].stock == "7"
    assert products["P1"].stock_status == "Normal"
    assert products["P1"].active is False
    assert repo._movements[0]["id"] == ids[0]
    assert repo._movements[0]["created_by"] == "admin"
    assert repo._movements[0]["confirmed_on"] is not None


def test_limits_are_validated_for_sum_of_same_product_lines():
    repo, products = repository(maximum=5)
    before = deepcopy(products)
    with pytest.raises(ValueError, match="máximo"):
        register(repo, (line(), line(ITEM2)))
    assert products == before
    assert repo._movements == []


def test_product_limit_precedes_company_limit():
    repo, products = repository(maximum=6, company_max=5)
    register(repo, (line(quantity=2),))
    assert products["P1"].stock == "6"


def test_company_limit_applies_when_product_has_none():
    repo, products = repository(company_max=5)
    with pytest.raises(ValueError, match="máximo"):
        register(repo, (line(quantity=2),))
    assert products["P1"].stock == "4"


def test_duplicate_movement_does_not_restock_twice():
    repo, products = repository()
    register(repo, (line(),))
    with pytest.raises(ValueError, match="repetida"):
        register(repo, (line(),))
    assert products["P1"].stock == "5"
    assert len(repo._movements) == 1


def test_failed_publication_restores_shared_objects():
    repo, products = repository()
    before = deepcopy(products)

    def fail():
        raise RuntimeError("Publicação falhou")

    with pytest.raises(RuntimeError):
        register(repo, (line(),), publish=fail)
    assert repo.products is products
    assert products == before
    assert repo._movements == []


@pytest.mark.parametrize("items", [None, [], iter(())])
def test_invalid_items_cannot_publish_success_without_stock_entries(items):
    repo, products = repository()
    published = []
    with pytest.raises(ValueError):
        register(repo, items, publish=lambda: published.append(True))
    assert products["P1"].stock == "4"
    assert published == []
    assert repo._movements == []

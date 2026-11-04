"""Reprodução local do contrato de leitura; não conecta ao Supabase."""
from types import SimpleNamespace

from stockflow.infrastructure.repositories.supabase_product_repository import (
    SupabaseProductRepository,
)


class Query:
    def __init__(self, rows):
        self.rows = rows

    def select(self, *_args):
        return self

    def eq(self, key, value):
        return Query([row for row in self.rows if row.get(key) == value])

    def in_(self, key, values):
        return Query([row for row in self.rows if row.get(key) in values])

    def limit(self, count):
        return Query(self.rows[:count])

    def order(self, *_args):
        return self

    def execute(self):
        return SimpleNamespace(data=self.rows)


def test_single_product_preserves_same_stock_limits_as_catalog():
    rows = {
        'products': [{'id': 'product-1', 'company_id': 'company-1',
                      'barcode': 'PRD-001', 'name': 'Produto', 'stock': 5,
                      'sell_price': '20.00', 'active': True}],
        'categories': [],
        'product_stock': [{'product_id': 'product-1',
                           'min_quantity': 10, 'max_quantity': 20}],
    }
    client = SimpleNamespace(table=lambda name: Query(rows[name]))
    repo = SupabaseProductRepository(client, 'company-1')
    catalog, _ = repo.fetch_catalog()
    assert (catalog['PRD-001'].minimum_stock, catalog['PRD-001'].maximum_stock) == (10, 20)
    product = repo.get('PRD-001')
    assert (product.minimum_stock, product.maximum_stock) == (10, 20)

from dataclasses import dataclass


@dataclass(frozen=True)
class Product:
    code: str
    name: str
    category: str
    unit: str
    sale_price: str
    cost: str
    active: bool
    stock: str
    stock_status: str


DEMO_PRODUCTS = {
    product.code: product
    for product in (
        Product('PRD-009', 'Monitor LG UltraWide 34"', 'Eletrônicos',
                'Unidade (UN)', 'R$ 2.499,90', 'R$ 1.850,00', True, '18', 'Normal'),
        Product('PRD-008', 'Teclado mecânico sem fio', 'Periféricos',
                'Unidade (UN)', 'R$ 459,90', 'R$ 280,00', True, '6', 'Baixo'),
        Product('PRD-007', 'Mouse ergonômico', 'Periféricos',
                'Unidade (UN)', 'R$ 189,90', 'R$ 95,00', True, '2', 'Crítico'),
    )
}

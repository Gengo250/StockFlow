from dataclasses import dataclass

from stockflow.domain.stock_level import NOT_CONFIGURED


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
    # Último campo, e com padrão, de propósito: há chamadores posicionais de
    # 9 argumentos (testes e fixtures) que construíam `Product` antes da US04
    # existir. Inserir o mínimo no meio trocaria silenciosamente o significado
    # dos argumentos deles.
    #
    # `stock_status` acima continua existindo porque é o que a ficha e a
    # listagem leem, mas ele é um CACHE: a fonte da verdade é
    # `derive_stock_status(stock, minimum_stock)`, e a tela de Estoque
    # recalcula a cada `apply_filters` em vez de confiar no valor gravado.
    #
    # Padrão "não configurado", igual ao `COALESCE(ps.min_quantity, 0)` do
    # banco: produto construído sem mínimo não tem limiar e não alerta.
    minimum_stock: int = NOT_CONFIGURED


# Catálogo de demonstração, montado para cobrir TODAS as faixas de
# `fn_stock_state` — inclusive a que a US04 manda excluir do alerta. Sem um
# produto por faixa, a tela fica sem como provar que a regra está certa.
#
#   saldo  mínimo  situação
#      18      10  Normal     (18 >= 12, que é 10 × 1,2)
#      11      10  Atenção    (acima do mínimo, mas a menos de 20% dele)
#       6      10  Baixo      (saldo <= mínimo)
#       2       5  Baixo      (mínimo do PRODUTO, não um limiar global)
#       0      10  Crítico    (sem unidade em mãos)
#       3       0  Normal     (SEM mínimo configurado: fora do alerta)
DEMO_PRODUCTS = {
    product.code: product
    for product in (
        Product('PRD-009', 'Monitor LG UltraWide 34"', 'Eletrônicos',
                'Unidade (UN)', 'R$ 2.499,90', 'R$ 1.850,00', True, '18', 'Normal',
                minimum_stock=10),
        Product('PRD-008', 'Teclado mecânico sem fio', 'Periféricos',
                'Unidade (UN)', 'R$ 459,90', 'R$ 280,00', True, '6', 'Baixo',
                minimum_stock=10),
        # Mínimo 5, menor que o padrão: existe para que o catálogo prove que a
        # regra usa o mínimo DO PRODUTO. Com um limiar global de 10, este item
        # e o PRD-008 seriam indistinguíveis.
        Product('PRD-007', 'Mouse ergonômico', 'Periféricos',
                'Unidade (UN)', 'R$ 189,90', 'R$ 95,00', True, '2', 'Baixo',
                minimum_stock=5),
        # Estoque zerado: o pior caso, e o primeiro na ordenação por
        # criticidade.
        Product('PRD-006', 'Headset USB com microfone', 'Eletrônicos',
                'Unidade (UN)', 'R$ 329,00', 'R$ 198,00', True, '0', 'Crítico',
                minimum_stock=10),
        # Faixa de aproximação: acima do mínimo, perto o bastante para
        # planejar reposição. É a faixa que não existia antes de a regra ser
        # alinhada com `fn_stock_state`.
        Product('PRD-005', 'Webcam Full HD', 'Eletrônicos',
                'Unidade (UN)', 'R$ 279,90', 'R$ 160,00', True, '11', 'Atenção',
                minimum_stock=10),
        # SEM mínimo configurado. Saldo baixo, mas fora do alerta: é o caso
        # que a US04 manda excluir, e tê-lo aqui é o que impede a exclusão de
        # voltar a ser quebrada sem ninguém perceber.
        Product('PRD-003', 'Cabo HDMI 2m', 'Eletrônicos',
                'Unidade (UN)', 'R$ 49,90', 'R$ 22,00', True, '3', 'Normal'),
    )
}

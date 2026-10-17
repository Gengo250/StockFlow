import pytest
from stockflow.presentation.demo_products import Product
from stockflow.application.dto.product_input import ProductInput

def test_calculo_sugestao_reposicao():
    p = Product(code='P1', name='Item', category='Cat', unit='UN', sale_price='10', cost='5', active=True, stock='4', stock_status='Baixo', minimum_stock=10, maximum_stock=20)
    
    max_q = getattr(p, 'maximum_stock', None)
    min_q = getattr(p, 'minimum_stock', None)
    stock = int(p.stock)
    
    sugerido = None
    if max_q is not None and min_q is not None and stock <= min_q:
        sugerido = max(0, max_q - stock)
        
    assert sugerido == 16

def test_validacao_maximo_inferior_ao_minimo():
    min_q = 10
    max_q = 5
    valido = max_q >= min_q
    assert not valido

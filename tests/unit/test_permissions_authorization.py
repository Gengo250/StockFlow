import pytest
from stockflow.domain.enums.user_role import UserRole
from stockflow.domain.exceptions.permission_denied import PermissionDeniedError
from stockflow.domain.permissions import (
    pode_ver,
    pode_gravar,
    ensure_can_manage_products,
    ensure_can_manage_users,
    ensure_can_move_stock,
)

def test_admin_full_access():
    admin = UserRole.ADMIN
    assert pode_ver(admin, "produtos")
    assert pode_gravar(admin, "produtos")
    assert pode_ver(admin, "usuarios")
    assert pode_gravar(admin, "usuarios")
    assert pode_ver(admin, "movimentacoes")
    assert pode_gravar(admin, "movimentacoes")

def test_stock_limited_access():
    stock = UserRole.STOCK
    assert pode_ver(stock, "produtos")
    assert pode_gravar(stock, "produtos")
    assert pode_ver(stock, "usuarios") is False
    assert pode_gravar(stock, "usuarios") is False

def test_seller_limited_access():
    seller = UserRole.SELLER
    assert pode_ver(seller, "produtos")
    assert pode_gravar(seller, "produtos") is False
    assert pode_ver(seller, "vendas")
    assert pode_gravar(seller, "vendas")

def test_permission_denied_exceptions():
    seller = UserRole.SELLER
    
    with pytest.raises(PermissionDeniedError):
        ensure_can_manage_products(seller)

    with pytest.raises(PermissionDeniedError):
        ensure_can_manage_users(seller)

    with pytest.raises(PermissionDeniedError):
        ensure_can_move_stock(seller)

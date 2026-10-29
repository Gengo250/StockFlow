import csv
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

from PySide6.QtCore import QDate
import pytest

from stockflow.domain.entities.session import Session
from stockflow.domain.enums.price_edit_field import PriceEditField
from stockflow.domain.enums.user_role import UserRole
from stockflow.domain.exceptions.permission_denied import PermissionDeniedError
from stockflow.application.dto.sale_filter import SalePage
from stockflow.presentation.pages.overview import ReportsPage


def _session(role=UserRole.ADMIN):
    return Session('user-1', 'Usuário', 'user@example.com', role)


def test_report_filters_metrics_export_and_failure(qapp, tmp_path):
    products = Mock()
    products.list_all.return_value = [
        SimpleNamespace(code='P1', name='Câmera', category='Imagem', stock='12', minimum_stock=5, active=True),
        SimpleNamespace(code='P2', name='=Formula', category='Telas', stock='3', minimum_stock=None, active=False),
    ]
    sales = Mock()
    sales.list_all.return_value = [
        dict(id='V1', cliente='Ana', produto='Câmera', total='1200.50', data='2026-10-14'),
        dict(id='V2', cliente='Bia', produto='Mouse', total='100', data='2026-10-13'),
    ]
    page = ReportsPage(products, sales, _session())
    page.refresh()
    assert [label.text() for _, label in page.metrics] == ['2', '15', '1']
    page.status.setCurrentText('Inativos')
    assert len(page.rows) == 1
    path = tmp_path / 'report.csv'
    page.export_csv(path)
    with path.open(encoding='utf-8-sig') as output:
        exported = list(csv.reader(output, delimiter=';'))
    assert len(exported) == 2
    assert exported[0][1] == 'Produto'
    assert exported[1][1] == "'=Formula"
    page.search.setText('ausente')
    assert not page.rows and not page.export_button.isEnabled()
    page.search.clear()
    page.kind.setCurrentText('Vendas')
    assert [label.text() for _, label in page.metrics] == ['2', 'R$ 1.300,50', 'R$ 650,25']
    page.search.setText('ana')
    assert len(page.rows) == 1
    assert page.table.item(0, 3).text() == 'R$ 1.200,50'
    sales.list_all.side_effect = RuntimeError('Sem conexão')
    page.refresh()
    assert not page.rows and page.table.rowCount() == 0
    assert not page.export_button.isEnabled()
    assert 'Sem conexão' in page.error.text()
    assert all(label.text() == '—' for _, label in page.metrics)
    sales.list_all.side_effect = None
    page.refresh()
    assert len(page.rows) == 1 and page.export_button.isEnabled()
    page.close()


def test_movement_and_audit_reports_export_filtered_rows(qapp, tmp_path):
    products = Mock()
    products.list_all.return_value = []
    sales = Mock()
    movements = Mock()
    movements.list_movements.return_value = (
        ('M1', 'P1', 'Café', 'Entrada', 8, 'Confirmada', 'Reposição', '29/10/2026',
         'Fornecedor', 'Compra'),
        ('M2', 'P1', 'Café', 'Saída', 3, 'Cancelada', 'Estorno', '28/10/2026',
         '—', '—'),
    )
    history = Mock()
    history.list_changes.return_value = (
        SimpleNamespace(
            changed_on=None, product_code='P1', product_name='Café',
            field=PriceEditField.SELL_PRICE, old_price=None,
            new_price=Decimal('12.50'), changed_by='Admin',
        ),
        SimpleNamespace(
            changed_on=None, product_code='P2', product_name='Ação',
            field=PriceEditField.BUY_PRICE, old_price=Decimal('9.00'),
            new_price=Decimal('10.00'), changed_by='Admin',
        ),
    )
    session = _session()
    page = ReportsPage(
        products, sales, session, movement_service=movements,
        price_history_service=history,
    )
    page.kind.setCurrentText('Movimentações')
    qapp.processEvents()
    assert len(page.rows) == 2
    assert page.metrics[1][1].text() == '8'
    page.status.setCurrentText('Confirmada')
    page.movement_kind_filter.setCurrentText('Entrada')
    assert len(page.rows) == 1
    movement_path = tmp_path / 'movimentacoes.csv'
    page.export_csv(movement_path)
    with movement_path.open(encoding='utf-8-sig') as output:
        movement_csv = list(csv.reader(output, delimiter=';'))
    assert movement_csv[0][0] == 'Movimentação'
    assert movement_csv[1][2] == 'Café'
    assert len(movement_csv) == 2

    page.kind.setCurrentText('Auditoria')
    qapp.processEvents()
    page.search.setText('café')
    assert len(page.rows) == 1
    audit_path = tmp_path / 'auditoria.csv'
    page.export_csv(audit_path)
    with audit_path.open(encoding='utf-8-sig') as output:
        audit_csv = list(csv.reader(output, delimiter=';'))
    assert audit_csv[0] == ['Quando', 'Produto', 'Campo', 'De', 'Para', 'Por']
    assert audit_csv[1][1] == 'P1 — Café'
    assert audit_csv[1][4] == 'R$ 12,50'
    history.list_changes.assert_called_once_with(session)
    page.close()


def test_report_choices_follow_read_permissions(qapp, tmp_path):
    products, sales = Mock(), Mock()
    stock_user = _session(UserRole.STOCK)
    page = ReportsPage(products, sales, stock_user)
    assert page.kind.findData('estoque') >= 0
    assert page.kind.findData('vendas') >= 0
    assert page.kind.findData('movimentacoes') >= 0
    assert page.kind.findData('auditoria') == -1
    page.close()
    admin_page = ReportsPage(products, sales, _session())
    admin_page.kind.setCurrentText('Auditoria')
    admin_page.session = _session(UserRole.SELLER)
    denied_path = tmp_path / 'denied.csv'
    with pytest.raises(PermissionDeniedError):
        admin_page.export_csv(denied_path)
    assert not denied_path.exists()
    admin_page.close()

    seller = ReportsPage(products, sales, _session(UserRole.SELLER))
    assert seller.kind.findData('movimentacoes') == -1
    assert seller.kind.findData('auditoria') == -1
    seller.close()


def test_sales_export_respects_period_client_seller_and_status(qapp, tmp_path):
    products, repository = Mock(), Mock()
    session = _session()
    sales = (
        {
            'id': 'V1', 'cliente': 'Ana', 'produto': 'Câmera', 'total': '100.00',
            'data': '14/10/2026 10:00', 'status': 'CONCLUIDA',
            'client_id': 'C1', 'seller_id': 'U1', 'seller': 'João',
        },
        {
            'id': 'V2', 'cliente': 'Bia', 'produto': 'Mouse', 'total': '50.00',
            'data': '15/10/2026 10:00', 'status': 'CANCELADA',
            'client_id': 'C2', 'seller_id': 'U2', 'seller': 'Maria',
        },
        {
            'id': 'V3', 'cliente': 'Ana', 'produto': 'Câmera', 'total': '20.00',
            'data': '14/10/2026 09:00', 'status': 'PENDENTE',
            'client_id': 'C1', 'seller_id': 'U1', 'seller': 'João',
        },
    )

    def list_sales(request_session, filtro, page, size):
        assert request_session == session
        matching = tuple(
            sale for sale in sales
            if (
                sale['status'] == 'PENDENTE'
                if filtro.status == 'PENDENTE'
                else sale['status'] != 'PENDENTE'
            )
        )
        return SalePage(matching, len(matching), page, size)

    service = Mock()
    service.list_sales.side_effect = list_sales
    page = ReportsPage(
        products, repository, session, sale_service=service,
    )
    page.kind.setCurrentText('Vendas')
    qapp.processEvents()
    assert len(page.rows) == 3
    page.status.setCurrentText('Concluída')
    page.client_filter.setCurrentIndex(page.client_filter.findData('C1'))
    page.seller_filter.setCurrentIndex(page.seller_filter.findData('U1'))
    page.date_start.setDate(QDate(2026, 10, 14))
    page.date_end.setDate(QDate(2026, 10, 14))
    page.period_filter.setChecked(True)
    assert len(page.rows) == 1
    assert page.metrics[1][1].text() == 'R$ 100,00'
    assert service.list_sales.call_count == 2
    path = tmp_path / 'vendas.csv'
    page.export_csv(path)
    with path.open(encoding='utf-8-sig') as output:
        rows = list(csv.reader(output, delimiter=';'))
    assert len(rows) == 2
    assert rows[1][1] == 'Ana'
    assert rows[1][6] == 'João'
    page.close()

"""Regressões da auditoria: mesmos cenários, com dados remotos explícitos no fake."""
import dataclasses
import os
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

ROOT = Path.cwd()
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tests' / 'unit')]
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

import pytest
from PySide6.QtCore import QSettings, QTimer
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QLineEdit, QMessageBox, QPushButton

from stockflow.application.dto.client_input import ClientInput
from stockflow.application.dto.movement_input import MovementInput
from stockflow.domain.enums.movement_kind import MovementKind
from stockflow.domain.enums.user_role import UserRole
from stockflow.infrastructure.repositories.demo_client_repository import DemoClientRepository
from stockflow.presentation import backend
from stockflow.presentation.app import LoginFlow
from stockflow.presentation.demo_accounts import conta_por_papel
from stockflow.presentation.demo_data import reset_demo_client_statuses
from stockflow.presentation.windows.main_window import MainWindow
from stockflow.presentation.widgets.user_form import UserForm
from stockflow.presentation.workers import executar_agora
from test_supabase_product_repository import COMPANY, ClienteFalso, catalogo_falso


@pytest.fixture(scope='session')
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    monkeypatch.setenv('STOCKFLOW_BACKEND', 'demo')
    reset_demo_client_statuses()
    for name in ('critical', 'warning', 'information'):
        monkeypatch.setattr(QMessageBox, name, lambda *a, **k: None)
    yield
    reset_demo_client_statuses()


@pytest.fixture
def window(qapp):
    w = MainWindow(conta_por_papel(UserRole.ADMIN).session())
    w.executar_em_segundo_plano = executar_agora
    yield w
    w.close()


@pytest.fixture
def remote_window(qapp, monkeypatch):
    client = ClienteFalso(catalogo_falso(), rpc_resultados={
        "fn_list_company_clients": [{"client_id": "client-a", "name": "Cliente teste", "active": True}],
        "fn_register_sale": "sale-a",
    })
    monkeypatch.setenv('STOCKFLOW_BACKEND', 'supabase')
    monkeypatch.setattr(backend, '_client', lambda: client)
    session = dataclasses.replace(conta_por_papel(UserRole.ADMIN).session(), company_id=COMPANY)
    w = MainWindow(session)
    w.executar_em_segundo_plano = executar_agora
    yield w, client
    w.close()


def choose_sale(page, value='10,00'):
    page.cliente_combo.setCurrentIndex(1)
    page.produto_combo.setCurrentIndex(1)
    page.val_input.setText(value)
    assert page.cliente_combo.currentData() and page.produto_combo.currentData()


def test_remote_clients_use_persistent_repository(remote_window):
    w, _ = remote_window
    assert not isinstance(w.clientes_page.repository, DemoClientRepository), 'Modo Supabase usa DemoClientRepository'


def test_remote_sale_reaches_rpc(remote_window):
    w, client = remote_window
    choose_sale(w.vendas_page)
    client.chamadas_rpc.clear()
    w.vendas_page._registrar_venda()
    assert any(name == 'fn_register_sale' for name, _ in client.chamadas_rpc), 'Venda só altera historico_vendas em memória'


def test_new_client_becomes_selectable_in_sales(window, qapp):
    page = window.clientes_page
    errors = []
    def fill_dialog():
        try:
            dialog = QApplication.activeModalWidget()
            assert isinstance(dialog, QDialog)
            fields = dialog.findChildren(QLineEdit)
            fields[0].setText('Cliente Auditoria Novo')
            dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Save).click()
        except Exception as e:
            errors.append(e)
            if QApplication.activeModalWidget():
                QApplication.activeModalWidget().reject()
    QTimer.singleShot(0, fill_dialog)
    page.new_client_button.click()
    assert not errors
    assert any(c.name == 'Cliente Auditoria Novo' for c in page.service.list_clients())
    combo = window.vendas_page.cliente_combo
    assert any((combo.itemData(i) or {}).get('nome') == 'Cliente Auditoria Novo' for i in range(combo.count())), 'Vendas recarrega DEMO_PEOPLE, não os clientes cadastrados'


@pytest.mark.parametrize('value', ['abc', '-10,00', 'NaN'])
def test_sale_rejects_invalid_amount(window, value):
    page = window.vendas_page
    choose_sale(page, value)
    before = len(page.historico_vendas)
    page._registrar_venda()
    assert len(page.historico_vendas) == before, f'Valor inválido aceito: {value}'


def test_sale_rechecks_inactive_client(window):
    page = window.vendas_page
    choose_sale(page)
    client_id = page.cliente_combo.currentData()['id']
    window.clientes_page.service.set_active(client_id, False)
    before = len(page.historico_vendas)
    page._registrar_venda()
    assert len(page.historico_vendas) == before, 'Combo antigo vende para cliente já inativado'


def test_stock_role_cannot_register_sale(qapp):
    w = MainWindow(conta_por_papel(UserRole.STOCK).session())
    try:
        choose_sale(w.vendas_page)
        before = len(w.vendas_page.historico_vendas)
        w.vendas_page._registrar_venda()
        assert len(w.vendas_page.historico_vendas) == before, 'SQL permite ADMIN/SELLER; UI aceita STOCK'
    finally:
        w.close()


def test_stock_role_cannot_create_client(qapp):
    w = MainWindow(conta_por_papel(UserRole.STOCK).session())
    try:
        assert not w.clientes_page.new_client_button.isEnabled(), 'SQL permite ADMIN/SELLER; UI libera cadastro a STOCK'
    finally:
        w.close()


def test_admin_user_form_has_save_path(qapp):
    form = UserForm(pode_gerenciar=True)
    try:
        save = next(b for b in form.findChildren(QPushButton) if b.text() == 'Cadastrar usuário')
        assert save.isEnabled(), 'Cadastro/edição de usuários não tem caminho de gravação'
    finally:
        form.close()


def test_relogin_rebuilds_company_repositories(remote_window, qapp, tmp_path):
    w, client = remote_window
    flow = LoginFlow(QSettings(str(tmp_path / 'settings.ini'), QSettings.IniFormat))
    flow.main = w
    company_b = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'
    next_session = dataclasses.replace(w.session, user_id='user-b', company_id=company_b)
    try:
        flow.logout()
        flow.open_main(next_session)
        assert flow.main.product_repository._company_id == company_b, 'Sessão muda, repositório continua na empresa anterior'
        assert not flow.main.products, 'Catálogo anterior não foi limpo no relogin'
    finally:
        flow.login.close()


def test_product_save_handles_connection_error(window, monkeypatch):
    window._show_new_product('produtos')
    def fail(*a, **k):
        raise RuntimeError('Falha de conexão simulada')
    monkeypatch.setattr(window.product_service, 'create_product', fail)
    window._save_new_product()
    assert window.last_save_error is not None


def test_demo_rejects_negative_stock_like_sql(window):
    page = window.movimentacoes_page
    window.show_page('movimentacoes')
    code = 'PRD-009'
    before = int(window.products[code].stock)
    page.produto_combo.setCurrentIndex(page.produto_combo.findData(code))
    page.especie_combo.setCurrentIndex(page.especie_combo.findData(MovementKind.SAIDA))
    page.quantidade_input.setValue(before + 1)
    page.registrar_confirmar_button.click()
    assert int(window.products[code].stock) == before, 'Demo aceita saldo -1; products CHECK (stock >= 0) recusa no banco'


def test_movement_rechecks_inactive_product(window):
    window.show_page('movimentacoes')
    page = window.movimentacoes_page
    code = 'PRD-009'
    page.produto_combo.setCurrentIndex(page.produto_combo.findData(code))
    page.especie_combo.setCurrentIndex(page.especie_combo.findData(MovementKind.SAIDA))
    row = next(p for p in window.estoque_page.produtos if p[0] == code)
    window.estoque_page.toggle_product_status(row)
    assert not window.products[code].active
    before = len(window.movement_repository.list_movements())
    page.registrar_button.click()
    assert len(window.movement_repository.list_movements()) == before, 'Movimentação aceita produto desativado após montar o combo'


def test_optional_product_fields_survive_reopen(window):
    window._show_new_product('produtos')
    page = window.novo_produto_page
    page.name_input.setText('Produto Auditoria')
    page.category_input.setCurrentIndex(1)
    page.sale_price_input.setValue(20)
    page.cost_price_input.setValue(10)
    page.basic_info_card.description_input.setPlainText('Descrição persistente de auditoria')
    code = page.code_input.text()
    page.save_button.click()
    assert code in window.products
    window._show_edit_product(window.products[code])
    assert window.editar_produto_page.basic_info_card.description_input.toPlainText() == 'Descrição persistente de auditoria', 'Descrição não faz parte do DTO/modelo/banco'


def test_control_pending_confirm_cancel_balance(window):
    code = 'PRD-009'
    before = int(window.products[code].stock)
    movement = window.movement_service.register(window.session, MovementInput(code, MovementKind.SAIDA, 1))
    assert int(window.products[code].stock) == before
    window._confirmar_movimentacao(movement)
    assert int(window.products[code].stock) == before - 1
    window._cancelar_movimentacao(movement)
    assert int(window.products[code].stock) == before


def test_control_seller_cannot_open_restricted_pages(qapp):
    w = MainWindow(conta_por_papel(UserRole.SELLER).session())
    try:
        for page in ('usuarios', 'movimentacoes', 'fornecedores'):
            assert w.show_page(page) is False
        assert not w.novo_produto_page.save_button.isEnabled()
    finally:
        w.close()


def test_logout_ends_supabase_session(remote_window, tmp_path):
    w, client = remote_window
    client.auth = SimpleNamespace(sign_out=Mock())
    flow = LoginFlow(QSettings(str(tmp_path / 'logout.ini'), QSettings.IniFormat))
    flow.main = w
    try:
        flow.logout()
        client.auth.sign_out.assert_called_once()
    finally:
        flow.login.close()


@pytest.mark.parametrize('view', ['vw_stock_situation', 'vw_stock_alerts'])
def test_view_migration_preserves_existing_column_prefix(view):
    """Contrato PostgreSQL: OR REPLACE só acrescenta colunas ao FINAL.

    Verificação estrutural, não substitui executar as migrations no Postgres.
    https://www.postgresql.org/docs/17/sql-createview.html
    """
    migrations = ROOT / 'database' / 'supabase' / 'migrations'
    before = (migrations / '20261004150000_minimum_stock_optional.sql').read_text()
    after = (migrations / '20261004160000_alert_view_carries_barcode.sql').read_text()
    def columns(sql):
        match = re.search(r'CREATE OR REPLACE VIEW public\.' + view + r'\s+.*?\bSELECT\b(.*?)\bFROM\b', sql, re.S | re.I)
        assert match, 'View não encontrada na migration'
        result = []
        for line in match.group(1).strip().splitlines():
            line = line.strip().rstrip(',').strip()
            alias = re.search(r'\bAS\s+(\w+)$', line, re.I)
            result.append(alias.group(1) if alias else line.rsplit('.', 1)[-1])
        return result
    old, new = columns(before), columns(after)
    assert new[:len(old)] == old, f'{view}: coluna nova desloca/renomeia colunas existentes em CREATE OR REPLACE VIEW'


# ---------------------------------------------------------------------------
# Invariantes abertas pela auditoria de 05/10/2026: a interface não pode
# oferecer o que o banco recusa, nem abrir numa tela diferente da marcada.
# ---------------------------------------------------------------------------

def test_demo_roles_are_real_database_roles():
    """A demonstração só usa papéis que `public.user_role` aceita.

    "Gerente", "Operador" e "Financeiro" não existem no enum: editar uma
    dessas pessoas abria o formulário num perfil que não era o dela, e
    salvar só poderia falhar no banco.
    """
    from stockflow.presentation.demo_users import USER_ROLES
    from stockflow.presentation.roles import ROLE_LABELS

    assert set(USER_ROLES) <= set(ROLE_LABELS.values()), (
        f"perfis da demonstração fora do enum do banco: "
        f"{sorted(set(USER_ROLES) - set(ROLE_LABELS.values()))}"
    )


def test_user_form_offers_exactly_the_database_roles(qapp):
    from stockflow.presentation.roles import ROLE_LABELS

    form = UserForm()
    try:
        ofertados = [form.role_input.itemText(i) for i in range(form.role_input.count())]
        gravados = [form.role_input.itemData(i) for i in range(form.role_input.count())]
        assert ofertados == list(ROLE_LABELS.values())
        assert gravados == [role.value for role in ROLE_LABELS]
    finally:
        form.close()


def test_every_demo_user_opens_the_form_on_their_own_role(qapp):
    """Perfil fora da oferta faz o combo cair no primeiro item, calado."""
    from stockflow.presentation.demo_users import DEMO_USERS

    for user in DEMO_USERS:
        form = UserForm(user)
        try:
            assert form.role_input.currentText() == user[3], user[0]
        finally:
            form.close()


def test_default_start_page_matches_the_active_sidebar_item(qapp):
    """Sem preferência salva, a janela abre na tela que o menu marca."""
    from stockflow.presentation.pages.overview import SettingsPage
    from stockflow.presentation.widgets.sidebar import DEFAULT_KEY

    vazio = QSettings(str(Path(os.environ.get('TMPDIR', '/tmp')) /
                          'stockflow-preferencias-inexistentes.ini'),
                      QSettings.IniFormat)
    vazio.clear()
    page = SettingsPage(None, settings=vazio)
    try:
        assert page.start_page.currentData() == DEFAULT_KEY
    finally:
        page.close()


def test_sales_client_combo_keeps_the_selection_across_a_reload(qapp):
    """Entrar em Vendas ressincroniza os clientes; a escolha tem que sobreviver."""
    from stockflow.presentation.pages.vendas import VendasPage

    page = VendasPage()
    try:
        page.cliente_combo.setCurrentIndex(1)
        escolhido = page.cliente_combo.currentData()
        assert escolhido
        page.recarregar_clientes_disponiveis()
        assert page.cliente_combo.currentData() == escolhido
    finally:
        page.close()


def test_single_trigger_guards_the_last_administrator():
    """Dois gatilhos para a mesma regra dão duas mensagens e dois SQLSTATE."""
    sql = "\n".join(
        p.read_text(encoding='utf-8')
        for p in sorted((ROOT / 'database' / 'code').rglob('*.sql'))
    )
    # Só as funções que recusam a remoção do último ADMIN; `updated_on` e
    # outros gatilhos de company_users não disputam esta regra.
    guardas = [
        nome for nome, corpo in re.findall(
            r"CREATE OR REPLACE FUNCTION public\.(\w+)\s*\(\)(.*?)\$\$;",
            sql, re.I | re.S,
        )
        if "administrador ativo" in corpo
    ]
    assert len(guardas) == 1, f"gatilhos concorrentes do último ADMIN: {guardas}"


def test_supplier_id_is_declared_once_in_the_declarative_schema():
    """ALTER ADD COLUMN repetindo a coluna do CREATE TABLE quebra o banco limpo."""
    tabelas = ROOT / 'database' / 'code' / 'tables'
    declaracoes = []
    for path in sorted(tabelas.glob('*.sql')):
        texto = re.sub(r"--[^\n]*", "", path.read_text(encoding='utf-8'))
        declaracoes += [path.name for _ in re.findall(
            r"^\s*supplier_id\s+uuid|ADD COLUMN\s+supplier_id\b", texto, re.I | re.M)]
    assert declaracoes.count('07_suppliers.sql') == 1, (
        f"supplier_id declarada mais de uma vez: {declaracoes}"
    )

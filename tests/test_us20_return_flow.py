"""Fluxo do botão existente de devolução com os diálogos padrão e o serviço US20."""
from copy import deepcopy

import pytest
from PySide6.QtWidgets import QInputDialog, QMessageBox

from stockflow.application.services.return_service import ReturnService
from stockflow.domain.enums.user_role import UserRole
from stockflow.presentation.demo_accounts import conta_por_papel
from stockflow.presentation.windows.main_window import MainWindow


@pytest.fixture
def context(qapp, monkeypatch, tmp_path):
    monkeypatch.setenv("STOCKFLOW_BACKEND", "demo")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    messages = []
    for name in ("critical", "warning", "information"):
        monkeypatch.setattr(
            QMessageBox, name, staticmethod(lambda parent, title, text: messages.append(text))
        )
    window = MainWindow(conta_por_papel(UserRole.ADMIN).session())
    window.cash_register_service.open(0)
    client = next(client for client in window.client_repository.list_all() if client.active)
    sale = window.sale_service.register_sale(window.session, client.client_id, [
        {"codigo": "PRD-009", "quantidade": 1}, {"codigo": "PRD-008", "quantidade": 2},
    ])
    window._show_sale_details(sale["id"])
    yield window, sale, messages
    window.close()


def choose(monkeypatch, *, full=True, quantities=None, reason="Conferência dos itens"):
    monkeypatch.setattr(QInputDialog, "getItem", staticmethod(
        lambda parent, title, label, options, *args: (options[0 if full else 1], True)
    ))
    quantities = quantities or {}
    monkeypatch.setattr(QInputDialog, "getInt", staticmethod(
        lambda parent, title, label, *args: (
            next((value for code, value in quantities.items() if f"[{code}]" in label), 0), True
        )
    ))
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *args: (reason, True)))


def balances(window):
    return {code: int(window.products[code].stock) for code in ("PRD-009", "PRD-008")}


def returns(window, sale):
    return [entry for entry in window.sale_repository.returns if entry["sale_id"] == sale["id"]]


def test_existing_buttons_support_partial_then_complete(context, monkeypatch):
    window, sale, _ = context
    page = window.sale_details_page
    original = deepcopy(page.venda["items"])
    before = balances(window)
    assert page.cancel_button.text() == "Cancelar venda"
    assert page.return_button.text() == "Registrar devolução"
    assert page.cancel_button.height() == page.return_button.height() == 40
    choose(monkeypatch, full=False, quantities={"PRD-008": 1})
    page.return_button.click()
    assert balances(window) == {**before, "PRD-008": before["PRD-008"] + 1}
    assert "parcial registrada" in page.return_feedback_label.text()
    assert "1 de 3" in page.return_summary_label.text()
    assert not page.cancel_button.isEnabled() and page.return_button.isEnabled()
    assert page.venda["items"] == original
    choose(monkeypatch)
    page.return_button.click()
    assert balances(window) == {"PRD-009": before["PRD-009"] + 1, "PRD-008": before["PRD-008"] + 2}
    assert len(returns(window, sale)) == 2
    assert returns(window, sale)[-1]["is_total_return"] is True
    assert page.venda["status"] == "CONCLUIDA"
    assert not page.cancel_button.isEnabled() and not page.return_button.isEnabled()


@pytest.mark.parametrize("stage", ["mode", "quantity", "reason"])
def test_aborting_any_dialog_does_not_write(context, monkeypatch, stage):
    window, sale, _ = context
    before = deepcopy((balances(window), window.sale_repository.returns, sale))
    choose(monkeypatch, full=False, quantities={"PRD-008": 1})
    method = {"mode": "getItem", "quantity": "getInt", "reason": "getText"}[stage]
    monkeypatch.setattr(QInputDialog, method, staticmethod(lambda *args: (0 if stage == "quantity" else "", False)))
    window.sale_details_page.return_button.click()
    assert (balances(window), window.sale_repository.returns, sale) == before
    assert window.sale_details_page.return_button.isEnabled()


@pytest.mark.parametrize("reason,quantity", [("", 1), ("   ", 1), ("Defeito", 0)])
def test_invalid_selection_does_not_write(context, monkeypatch, reason, quantity):
    window, sale, _ = context
    before = balances(window)
    choose(monkeypatch, full=False, quantities={"PRD-008": quantity}, reason=reason)
    window.sale_details_page.return_button.click()
    assert not returns(window, sale)
    assert balances(window) == before


def test_refusal_does_not_leave_previous_success_visible(context, monkeypatch):
    window, sale, messages = context
    choose(monkeypatch, full=False, quantities={"PRD-008": 1})
    window.sale_details_page.return_button.click()
    before = balances(window)
    assert not window.sale_details_page.return_feedback_label.isHidden()
    def refuse(self, request):
        raise ValueError("Quantidade não está mais disponível")
    monkeypatch.setattr(ReturnService, "create_return", refuse)
    choose(monkeypatch)
    window.sale_details_page.return_button.click()
    assert window.sale_details_page.return_feedback_label.isHidden()
    assert "Quantidade não está mais disponível" in messages[-1]
    assert balances(window) == before and len(returns(window, sale)) == 1
    assert not window._pending_sale_returns


def test_lost_response_reuses_same_request_without_duplicate_stock(context, monkeypatch):
    window, sale, messages = context
    original = ReturnService.create_return
    calls = []
    def lose_first_response(self, request):
        calls.append(request)
        result = original(self, request)
        if len(calls) == 1:
            raise TimeoutError("Resposta perdida após commit")
        return result
    monkeypatch.setattr(ReturnService, "create_return", lose_first_response)
    choose(monkeypatch)
    window.sale_details_page.return_button.click()
    after_commit = balances(window)
    window._refresh_sale_returnability(sale["id"])
    assert window.sale_details_page.return_button.isEnabled()
    assert not window.sale_details_page.cancel_button.isEnabled()
    assert "não foi confirmado" in messages[-1]
    assert window.sale_details_page.return_feedback_label.isHidden()
    def do_not_ask_again(*args):
        raise AssertionError("A operação pendente não pode receber nova seleção.")
    monkeypatch.setattr(QInputDialog, "getItem", staticmethod(do_not_ask_again))
    window.sale_details_page.return_button.click()
    assert calls[0] is calls[1]
    assert balances(window) == after_commit and len(returns(window, sale)) == 1
    assert not window._pending_sale_returns
    assert "completa registrada" in window.sale_details_page.return_feedback_label.text()


def test_invalid_response_preserves_request_without_success(context, monkeypatch):
    window, sale, messages = context
    choose(monkeypatch)
    monkeypatch.setattr(ReturnService, "create_return", lambda self, request: {"status": "COMPLETED"})
    window.sale_details_page.return_button.click()
    assert window._pending_sale_returns
    assert window.sale_details_page.return_feedback_label.isHidden()
    assert not returns(window, sale)
    assert "não foi confirmado" in messages[-1]


def test_late_read_from_previous_session_cannot_open_prompts_or_write(context, monkeypatch):
    window, sale, _ = context
    jobs = []
    window._execute = lambda *job: jobs.append(job)
    choose(monkeypatch)
    window.sale_details_page.return_button.click()
    fetch, loaded, _ = jobs[0]
    window.apply_session(conta_por_papel(UserRole.SELLER).session())
    loaded(fetch())
    assert not returns(window, sale)
    assert window.sale_details_page.venda is None


@pytest.mark.parametrize("role", [UserRole.SELLER, UserRole.STOCK])
def test_unauthorized_profile_cannot_execute_return(context, monkeypatch, role):
    window, sale, messages = context
    choose(monkeypatch)
    window.apply_session(conta_por_papel(role).session())
    window._devolver_venda(sale["id"])
    assert not returns(window, sale)
    assert messages

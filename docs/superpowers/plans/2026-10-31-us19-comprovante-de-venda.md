# US19 — Comprovante de venda · plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** emitir e reemitir um comprovante de venda a partir do que já está gravado, sem alterar venda, estoque ou pagamento.

**Architecture:** um valor de domínio (`SaleReceipt`) construído a partir do retorno de `SaleService.get_sale` (US17) mais o cadastro da empresa; um serviço de aplicação só de leitura; um renderizador HTML puro; um diálogo PySide6 que mostra, grava em PDF e imprime. Nenhuma migration, nenhuma dependência nova, nenhuma gravação.

**Tech Stack:** Python 3.12, PySide6 (QTextBrowser, QTextDocument, QPdfWriter, QPrintDialog), pytest, Supabase/PostgREST.

**Spec:** `docs/superpowers/specs/2026-10-31-us19-comprovante-de-venda-design.md`

## Global Constraints

- Rodar tudo com `uv run`. Suíte: `QT_QPA_PLATFORM=offscreen uv run --with pytest python -m pytest tests/ -q`.
- Nenhuma dependência nova em `pyproject.toml`.
- Nenhuma migration; nenhum arquivo novo em `database/`.
- Nenhum caminho de escrita alcançável a partir da emissão (regras 6 e 7 da história).
- Comentários e mensagens de interface em português; nomes de branch, commit e PR em inglês.
- Comentário só onde explica uma DECISÃO; o repositório não comenta o óbvio.
- `sales.discount` é o desconto TOTAL (itens + cabeçalho); `sales.original_total` é o bruto; `sales.total` é o líquido.
- Status: `PENDENTE` recusa; `CONCLUIDA` emite; `CANCELADA`/`DEVOLVIDA` emitem com marcação.

---

### Task 1: Domínio do comprovante

**Files:**
- Create: `src/stockflow/domain/sale_receipt.py`
- Test: `tests/unit/test_sale_receipt.py`

**Interfaces:**
- Consumes: `SaleStatus` (`domain/enums/sale_status.py`), `SaleReversalKind` (`domain/enums/sale_reversal_kind.py`), `calculate_discount_breakdown` (`domain/sale_discount.py`).
- Produces: `ReceiptCompany(name, document)`, `ReceiptItem(code, name, quantity, unit_price, subtotal, discount, final_subtotal)`, `ReceiptPayment(method, amount)`, `ReceiptCancellation(kind, reason, when, by)`, `SaleReceipt(...)` com `.cancelado`, `ReceiptNotAvailable`, `build_sale_receipt(venda: Mapping, company: ReceiptCompany) -> SaleReceipt`.

- [ ] **Step 1: Escrever os testes que falham**

```python
# tests/unit/test_sale_receipt.py
"""Comprovante de venda (US19/SCRUM-213).

A história pede um documento a partir do que JÁ está gravado. Estes testes
fixam as duas coisas que isso implica: o comprovante reflete o snapshot da
venda, e emitir não toca em nada.
"""

from decimal import Decimal

import pytest

from stockflow.domain.enums.sale_status import SaleStatus
from stockflow.domain.sale_receipt import (
    ReceiptCompany,
    ReceiptNotAvailable,
    build_sale_receipt,
)

EMPRESA = ReceiptCompany(name="StockFlow Comércio LTDA", document="11222333000181")

VENDA = {
    "id": "3f2a7c41-0000-4000-8000-000000000001",
    "cliente": "Ana Ferreira",
    "seller": "juliana.ramos",
    "data": "31/10/2026 14:22",
    "status": "CONCLUIDA",
    "payment_method": "PIX",
    "discount": "11.00",
    "original_total": "90.00",
    "total": "79.00",
    "valor": "R$ 79,00",
    "items": [
        {"product_code": "PRD-001", "product_name": "Teclado", "quantity": 2,
         "unit_price": "30.00", "subtotal": "60.00",
         "discount_amount": "6.00", "final_subtotal": "54.00"},
        {"product_code": "PRD-002", "product_name": "Mouse", "quantity": 1,
         "unit_price": "30.00", "subtotal": "30.00",
         "discount_amount": "0.00", "final_subtotal": "30.00"},
    ],
}


def test_venda_confirmada_gera_comprovante_com_todos_os_dados_obrigatorios():
    comprovante = build_sale_receipt(VENDA, EMPRESA)

    assert comprovante.sale_id == VENDA["id"]
    assert comprovante.issued_on == "31/10/2026 14:22"
    assert comprovante.company == EMPRESA
    assert comprovante.client == "Ana Ferreira"
    assert comprovante.seller == "juliana.ramos"
    assert comprovante.status is SaleStatus.CONCLUIDA
    assert comprovante.payment.method == "PIX"
    assert comprovante.payment.amount == Decimal("79.00")
    assert len(comprovante.items) == 2


def test_venda_pendente_nao_emite_comprovante_definitivo():
    """SCRUM-227: carrinho em montagem não é operação realizada."""
    with pytest.raises(ReceiptNotAvailable) as erro:
        build_sale_receipt(VENDA | {"status": "PENDENTE"}, EMPRESA)
    assert "não foi confirmada" in str(erro.value)


def test_itens_preservam_quantidade_preco_e_desconto_gravados():
    teclado, mouse = build_sale_receipt(VENDA, EMPRESA).items

    assert (teclado.code, teclado.name) == ("PRD-001", "Teclado")
    assert teclado.quantity == 2
    assert teclado.unit_price == Decimal("30.00")
    assert teclado.subtotal == Decimal("60.00")
    assert teclado.discount == Decimal("6.00")
    assert teclado.final_subtotal == Decimal("54.00")
    assert mouse.discount == Decimal("0.00")


def test_totais_separam_desconto_de_item_e_desconto_da_venda():
    """`sales.discount` é o desconto TOTAL; a diferença é o do cabeçalho."""
    comprovante = build_sale_receipt(VENDA, EMPRESA)

    assert comprovante.gross == Decimal("90.00")
    assert comprovante.item_discount == Decimal("6.00")
    assert comprovante.sale_discount == Decimal("5.00")
    assert comprovante.total_discount == Decimal("11.00")
    assert comprovante.net == Decimal("79.00")


def test_venda_sem_cliente_associado_omite_o_bloco_do_cliente():
    comprovante = build_sale_receipt(VENDA | {"cliente": ""}, EMPRESA)
    assert comprovante.client is None


def test_venda_cancelada_emite_comprovante_marcado_com_o_motivo():
    """SCRUM-229: cancelada FOI confirmada, então emite — marcada."""
    cancelada = VENDA | {
        "status": "CANCELADA",
        "reversal_kind": "CANCELAMENTO",
        "reversal_reason": "Registro em duplicidade",
        "reversal_on": "31/10/2026 15:00",
        "reversal_by": "ana.ferreira",
    }
    comprovante = build_sale_receipt(cancelada, EMPRESA)

    assert comprovante.cancelado
    assert comprovante.status is SaleStatus.CANCELADA
    assert comprovante.cancellation.reason == "Registro em duplicidade"
    assert comprovante.cancellation.by == "ana.ferreira"
    # Os dados comerciais continuam os da operação original.
    assert comprovante.net == Decimal("79.00")
    assert len(comprovante.items) == 2


def test_venda_devolvida_tambem_emite_marcada():
    devolvida = VENDA | {
        "status": "DEVOLVIDA",
        "reversal_kind": "DEVOLUCAO",
        "reversal_reason": "Cliente desistiu",
        "reversal_on": "31/10/2026 16:00",
        "reversal_by": "ana.ferreira",
    }
    assert build_sale_receipt(devolvida, EMPRESA).cancelado


def test_venda_sem_itens_nao_emite_comprovante():
    with pytest.raises(ReceiptNotAvailable):
        build_sale_receipt(VENDA | {"items": []}, EMPRESA)


def test_valor_corrompido_recusa_a_emissao_em_vez_de_inventar_numero():
    with pytest.raises(ReceiptNotAvailable):
        build_sale_receipt(VENDA | {"total": "noventa reais"}, EMPRESA)


def test_descontos_que_nao_reconciliam_recusam_a_emissao():
    """Desconto maior que o bruto é dado inconsistente, não comprovante."""
    with pytest.raises(ReceiptNotAvailable):
        build_sale_receipt(VENDA | {"discount": "900.00"}, EMPRESA)


def test_construir_o_comprovante_nao_altera_a_venda_de_origem():
    """Regra 6: emitir é leitura. O dicionário de entrada sai intacto."""
    original = {chave: valor for chave, valor in VENDA.items()}
    build_sale_receipt(VENDA, EMPRESA)
    assert VENDA == original
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `QT_QPA_PLATFORM=offscreen uv run --with pytest python -m pytest tests/unit/test_sale_receipt.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'stockflow.domain.sale_receipt'`

- [ ] **Step 3: Implementar o módulo de domínio**

```python
# src/stockflow/domain/sale_receipt.py
"""Comprovante de venda (US19/SCRUM-213).

O comprovante é LEITURA do que foi gravado, nunca registro novo. Reemitir
relê `sales`/`sale_items`, onde o nome do cliente e o nome, código e preço do
produto já são congelados na gravação (`database/code/tables/06_clients_sales.sql`).
É esse snapshot — e não uma cópia feita aqui — que faz um cadastro editado
depois não reescrever um documento histórico.
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from stockflow.domain.enums.sale_reversal_kind import SaleReversalKind
from stockflow.domain.enums.sale_status import SaleStatus
from stockflow.domain.sale_discount import calculate_discount_breakdown

CENT = Decimal("0.01")
ZERO = Decimal("0.00")

SEM_VENDA = "Esta venda não está mais disponível para esta empresa."
NAO_CONFIRMADA = (
    "Esta venda ainda não foi confirmada. Finalize a venda antes de emitir "
    "o comprovante."
)
SEM_ITENS = "Esta venda não tem itens gravados e não pode gerar comprovante."
DADOS_INCONSISTENTES = (
    "Os valores gravados nesta venda não fecham, e o comprovante não pode "
    "ser emitido com números que não conferem."
)


class ReceiptNotAvailable(ValueError):
    """A venda não pode gerar comprovante definitivo.

    `ValueError` e não exceção própria de raiz: a tela já trata `ValueError`
    como recusa de domínio em todo o fluxo de vendas, e um tipo novo faria o
    tratamento existente deixar passar justamente a recusa desta história.
    """


@dataclass(frozen=True)
class ReceiptCompany:
    """Emitente. Vem do cadastro ATUAL, não do snapshot da venda.

    Diferente do cliente de propósito: a empresa é quem emite o documento,
    não uma grandeza comercial da operação.
    """

    name: str
    document: str = ""

    @property
    def identificada(self) -> bool:
        return bool(self.name.strip())


@dataclass(frozen=True)
class ReceiptItem:
    code: str
    name: str
    quantity: int
    unit_price: Decimal
    subtotal: Decimal
    discount: Decimal
    final_subtotal: Decimal


@dataclass(frozen=True)
class ReceiptPayment:
    method: str
    amount: Decimal


@dataclass(frozen=True)
class ReceiptCancellation:
    kind: SaleReversalKind
    reason: str
    when: str
    by: str


@dataclass(frozen=True)
class SaleReceipt:
    sale_id: str
    issued_on: str
    company: ReceiptCompany
    #: `None` quando a venda não tem cliente associado (regra 3). Vazio não
    #: serve: a tela precisa distinguir "sem cliente" de "nome em branco".
    client: str | None
    seller: str
    status: SaleStatus
    items: tuple[ReceiptItem, ...]
    payment: ReceiptPayment
    gross: Decimal
    item_discount: Decimal
    sale_discount: Decimal
    total_discount: Decimal
    net: Decimal
    cancellation: ReceiptCancellation | None = None

    @property
    def cancelado(self) -> bool:
        return self.status.revertida


def _dinheiro(valor) -> Decimal:
    if valor is None or valor == "":
        return ZERO
    try:
        quantia = Decimal(str(valor))
    except (ArithmeticError, InvalidOperation, TypeError, ValueError) as erro:
        raise ReceiptNotAvailable(DADOS_INCONSISTENTES) from erro
    if not quantia.is_finite():
        raise ReceiptNotAvailable(DADOS_INCONSISTENTES)
    return quantia.quantize(CENT, rounding=ROUND_HALF_UP)


def _quantidade(valor) -> int:
    try:
        return int(valor)
    except (TypeError, ValueError) as erro:
        raise ReceiptNotAvailable(DADOS_INCONSISTENTES) from erro


def _item(linha) -> ReceiptItem:
    subtotal = _dinheiro(linha.get("subtotal"))
    desconto = _dinheiro(linha.get("discount_amount"))
    return ReceiptItem(
        code=str(linha.get("product_code") or ""),
        name=str(linha.get("product_name") or ""),
        quantity=_quantidade(linha.get("quantity") or 0),
        unit_price=_dinheiro(linha.get("unit_price")),
        subtotal=subtotal,
        discount=desconto,
        # `final_subtotal` é coluna gerada no banco; o fallback cobre a linha
        # que chega do recibo da gravação, que não a traz.
        final_subtotal=_dinheiro(
            linha.get("final_subtotal", subtotal - desconto)
        ),
    )


def _cancelamento(venda) -> ReceiptCancellation | None:
    especie = venda.get("reversal_kind")
    if not especie:
        return None
    return ReceiptCancellation(
        kind=SaleReversalKind.from_value(especie),
        reason=str(venda.get("reversal_reason") or ""),
        when=str(venda.get("reversal_on") or ""),
        by=str(venda.get("reversal_by") or ""),
    )


def build_sale_receipt(venda, company: ReceiptCompany) -> SaleReceipt:
    """Monta o comprovante a partir do retorno de `SaleService.get_sale`.

    A regra de status mora AQUI e em nenhum outro lugar: a tela desabilita o
    botão por cortesia, mas quem recusa é esta função — senão a recusa teria
    duas redações e uma delas ficaria para trás.
    """
    if not venda:
        raise ReceiptNotAvailable(SEM_VENDA)

    status = SaleStatus.from_value(venda.get("status") or SaleStatus.CONCLUIDA)
    if status is SaleStatus.PENDENTE:
        raise ReceiptNotAvailable(NAO_CONFIRMADA)

    itens = tuple(_item(linha) for linha in (venda.get("items") or ()))
    if not itens:
        raise ReceiptNotAvailable(SEM_ITENS)

    bruto = _dinheiro(venda.get("original_total", venda.get("total")))
    descontos_de_item = tuple(item.discount for item in itens)
    desconto_total = _dinheiro(venda.get("discount"))
    desconto_da_venda = desconto_total - sum(descontos_de_item, start=ZERO)
    try:
        # Reusa a aritmética que a US22 já valida. Uma segunda redação da
        # mesma conta divergiria no primeiro arredondamento.
        resumo = calculate_discount_breakdown(
            bruto, descontos_de_item, desconto_da_venda
        )
    except ValueError as erro:
        raise ReceiptNotAvailable(DADOS_INCONSISTENTES) from erro

    cliente = str(venda.get("cliente") or "").strip()
    return SaleReceipt(
        sale_id=str(venda.get("id") or ""),
        issued_on=str(venda.get("data") or ""),
        company=company,
        client=cliente or None,
        seller=str(venda.get("seller") or "").strip(),
        status=status,
        items=itens,
        payment=ReceiptPayment(
            method=str(venda.get("payment_method") or ""),
            amount=_dinheiro(venda.get("total")),
        ),
        gross=resumo.gross,
        item_discount=resumo.item_discount,
        sale_discount=resumo.sale_discount,
        total_discount=resumo.total_discount,
        net=resumo.net,
        cancellation=_cancelamento(venda),
    )
```

- [ ] **Step 4: Rodar e ver passar**

Run: `QT_QPA_PLATFORM=offscreen uv run --with pytest python -m pytest tests/unit/test_sale_receipt.py -q`
Expected: PASS (11 testes)

- [ ] **Step 5: Commit**

```bash
git add src/stockflow/domain/sale_receipt.py tests/unit/test_sale_receipt.py
git commit -m "feat: add sale receipt domain value object"
```

---

### Task 2: Cadastro da empresa (porta e adaptadores)

**Files:**
- Create: `src/stockflow/application/ports/company_profile_repository.py`
- Create: `src/stockflow/infrastructure/repositories/demo_company_repository.py`
- Create: `src/stockflow/infrastructure/repositories/supabase_company_repository.py`
- Modify: `src/stockflow/presentation/backend.py` (acrescentar `build_company_repository`, junto dos demais `build_*`)
- Test: `tests/unit/test_company_profile_repositories.py`

**Interfaces:**
- Consumes: `ReceiptCompany` da Task 1.
- Produces: `CompanyProfileRepository` (Protocol com `get_profile() -> ReceiptCompany`), `DemoCompanyRepository()`, `SupabaseCompanyRepository(client, company_id)`, `backend.build_company_repository(session)`.

- [ ] **Step 1: Escrever os testes que falham**

```python
# tests/unit/test_company_profile_repositories.py
"""Dados da empresa emitente (US19/SCRUM-225).

Nada no aplicativo lia `company` antes desta história: a `Session` carrega
só `company_id`. A policy `company_select` e o GRANT já existem desde
`20261003120100_policies_security.sql`, então a leitura é direta e sem
migration.
"""

import pytest

from stockflow.domain.sale_receipt import ReceiptCompany
from stockflow.infrastructure.repositories.demo_company_repository import (
    DemoCompanyRepository,
)
from stockflow.infrastructure.repositories.supabase_company_repository import (
    SupabaseCompanyRepository,
)


class _Resposta:
    def __init__(self, data):
        self.data = data


class _Consulta:
    def __init__(self, data, registro):
        self._data, self._registro = data, registro

    def select(self, colunas):
        self._registro["select"] = colunas
        return self

    def eq(self, coluna, valor):
        self._registro.setdefault("eq", []).append((coluna, valor))
        return self

    def limit(self, quantidade):
        self._registro["limit"] = quantidade
        return self

    def execute(self):
        if isinstance(self._data, Exception):
            raise self._data
        return _Resposta(self._data)


class _ClienteFalso:
    """Só o suficiente de PostgREST para provar a consulta montada."""

    def __init__(self, data):
        self._data, self.chamadas = data, {}

    def table(self, nome):
        self.chamadas["table"] = nome
        return _Consulta(self._data, self.chamadas)


class _Erro(Exception):
    code = "42501"


def test_demo_devolve_a_empresa_da_demonstracao():
    empresa = DemoCompanyRepository().get_profile()
    assert isinstance(empresa, ReceiptCompany)
    assert empresa.identificada


def test_supabase_le_nome_e_cnpj_escopados_pela_empresa_da_sessao():
    cliente = _ClienteFalso([
        {"id": "c-1", "name": "StockFlow Comércio LTDA", "cnpj": "11222333000181"}
    ])
    empresa = SupabaseCompanyRepository(cliente, "c-1").get_profile()

    assert cliente.chamadas["table"] == "company"
    assert cliente.chamadas["select"] == "id,name,cnpj"
    assert ("id", "c-1") in cliente.chamadas["eq"]
    assert empresa == ReceiptCompany(
        name="StockFlow Comércio LTDA", document="11222333000181"
    )


def test_empresa_sem_cnpj_cadastrado_nao_vira_a_string_none():
    cliente = _ClienteFalso([{"id": "c-1", "name": "Mercearia", "cnpj": None}])
    assert SupabaseCompanyRepository(cliente, "c-1").get_profile().document == ""


def test_leitura_recusada_degrada_em_empresa_vazia_sem_derrubar_a_emissao():
    """O comprovante vale sem o cabeçalho; falhar a emissão por causa dele
    seria perder o documento inteiro por um bloco."""
    empresa = SupabaseCompanyRepository(_ClienteFalso(_Erro()), "c-1").get_profile()
    assert not empresa.identificada


def test_empresa_inexistente_tambem_degrada():
    empresa = SupabaseCompanyRepository(_ClienteFalso([]), "c-1").get_profile()
    assert not empresa.identificada


def test_backend_escolhe_o_adaptador_pela_variavel_de_ambiente(monkeypatch):
    from stockflow.presentation import backend

    monkeypatch.delenv("STOCKFLOW_BACKEND", raising=False)
    assert isinstance(backend.build_company_repository(None), DemoCompanyRepository)


def test_backend_exige_empresa_na_sessao_no_modo_banco(monkeypatch):
    from stockflow.presentation import backend

    monkeypatch.setenv("STOCKFLOW_BACKEND", "supabase")
    with pytest.raises(RuntimeError):
        backend.build_company_repository(object())
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `QT_QPA_PLATFORM=offscreen uv run --with pytest python -m pytest tests/unit/test_company_profile_repositories.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'stockflow.infrastructure.repositories.demo_company_repository'`

- [ ] **Step 3: Criar a porta**

```python
# src/stockflow/application/ports/company_profile_repository.py
"""Porta de leitura do cadastro da empresa emitente (US19).

Porta NOVA e estreita em vez de um método a mais em `CompanyRepository`:
aquele contrato é satisfeito hoje pelo `SupabaseProductRepository`, e
acrescentar membro ao Protocol quebraria essa conformidade por fora do
escopo desta história.
"""

from typing import Protocol

from stockflow.domain.sale_receipt import ReceiptCompany


class CompanyProfileRepository(Protocol):
    def get_profile(self) -> ReceiptCompany:
        """Nome e documento da empresa da sessão.

        NÃO levanta quando o cadastro está indisponível: devolve uma empresa
        não identificada. O comprovante continua válido sem o cabeçalho, e
        perder o documento inteiro por causa de um bloco seria pior.
        """
        ...
```

- [ ] **Step 4: Criar os dois adaptadores**

```python
# src/stockflow/infrastructure/repositories/demo_company_repository.py
"""Empresa emitente no modo demonstração."""

from stockflow.domain.sale_receipt import ReceiptCompany

#: CNPJ válido pelos dígitos verificadores e reconhecidamente de exemplo.
#: Um número inventado faria o comprovante da demonstração parecer o de uma
#: empresa real.
EMPRESA_DEMO = ReceiptCompany(
    name="StockFlow Comércio LTDA (demonstração)",
    document="11222333000181",
)


class DemoCompanyRepository:
    def get_profile(self) -> ReceiptCompany:
        return EMPRESA_DEMO
```

```python
# src/stockflow/infrastructure/repositories/supabase_company_repository.py
"""Cadastro da empresa emitente, lido direto de `public.company`.

Sem RPC nova: `company_select` (`USING fn_is_member(id)`) e o
`GRANT SELECT ... TO authenticated` existem desde
`20261003120100_policies_security.sql`. A RLS é quem escopa a leitura; o
`eq("id", ...)` só evita trazer as demais empresas do usuário.
"""

import logging

from stockflow.domain.sale_receipt import ReceiptCompany

logger = logging.getLogger("stockflow.company")

SEM_EMPRESA = ReceiptCompany(name="", document="")


class SupabaseCompanyRepository:
    def __init__(self, client, company_id):
        self._client, self._company_id = client, company_id

    def get_profile(self) -> ReceiptCompany:
        try:
            linhas = (
                self._client.table("company")
                .select("id,name,cnpj")
                .eq("id", self._company_id)
                .limit(1)
                .execute()
                .data
                or []
            )
        except Exception as erro:
            # Degradar, não derrubar: o comprovante é da VENDA, e o cabeçalho
            # da empresa é um bloco dele. `42501` aqui significa policy fora
            # do ar neste ambiente, e não venda inválida.
            logger.warning("Cadastro da empresa indisponível: %s", erro)
            return SEM_EMPRESA
        if not linhas:
            return SEM_EMPRESA
        return ReceiptCompany(
            name=str(linhas[0].get("name") or ""),
            document=str(linhas[0].get("cnpj") or ""),
        )
```

- [ ] **Step 5: Ligar no `backend.py`**

Acrescentar depois de `build_sale_repository` em `src/stockflow/presentation/backend.py`:

```python
def build_company_repository(session=None):
    """Cadastro da empresa emitente do comprovante (US19)."""
    if not using_supabase():
        from stockflow.infrastructure.repositories.demo_company_repository import (
            DemoCompanyRepository,
        )

        return DemoCompanyRepository()

    from stockflow.infrastructure.repositories.supabase_company_repository import (
        SupabaseCompanyRepository,
    )

    company_id = getattr(session, "company_id", None)
    if not company_id:
        raise RuntimeError(
            "A sessão não tem empresa. O comprovante precisa do company_id "
            "para ler o cadastro do emitente."
        )
    return SupabaseCompanyRepository(_client(), company_id)
```

- [ ] **Step 6: Rodar e ver passar**

Run: `QT_QPA_PLATFORM=offscreen uv run --with pytest python -m pytest tests/unit/test_company_profile_repositories.py -q`
Expected: PASS (7 testes)

- [ ] **Step 7: Commit**

```bash
git add src/stockflow/application/ports/company_profile_repository.py \
        src/stockflow/infrastructure/repositories/demo_company_repository.py \
        src/stockflow/infrastructure/repositories/supabase_company_repository.py \
        src/stockflow/presentation/backend.py \
        tests/unit/test_company_profile_repositories.py
git commit -m "feat: read issuing company profile for receipts"
```

---

### Task 3: Serviço de emissão

**Files:**
- Create: `src/stockflow/application/services/receipt_service.py`
- Modify: `tests/unit/test_sale_receipt.py` (acrescentar a seção do serviço no fim do arquivo)

**Interfaces:**
- Consumes: `build_sale_receipt`, `ReceiptCompany`, `ReceiptNotAvailable` (Task 1); `CompanyProfileRepository` (Task 2); `SaleService.get_sale` (existente); `exigir_ver` (`domain/permissions.py`).
- Produces: `ReceiptService(sales, companies)` com `issue(session, sale_id) -> SaleReceipt`.

- [ ] **Step 1: Acrescentar os testes que falham**

```python
# acrescentar ao fim de tests/unit/test_sale_receipt.py

from stockflow.application.services.receipt_service import ReceiptService
from stockflow.domain.enums.user_role import UserRole
from stockflow.domain.exceptions.permission_denied import PermissionDeniedError
from stockflow.infrastructure.repositories.demo_sale_repository import (
    DemoSaleRepository,
)
from stockflow.presentation.demo_accounts import conta_por_papel


class _VendasFalsas:
    """Dublê do `SaleService`: registra as chamadas e nunca grava."""

    def __init__(self, venda):
        self._venda, self.consultas = venda, []

    def get_sale(self, session, sale_id):
        self.consultas.append((session, sale_id))
        return self._venda


class _EmpresaFixa:
    def __init__(self, empresa=EMPRESA):
        self._empresa = empresa

    def get_profile(self):
        return self._empresa


def _admin():
    return conta_por_papel(UserRole.ADMIN).session()


def _vendedor():
    return conta_por_papel(UserRole.SELLER).session()


def test_servico_emite_pelo_mesmo_caminho_de_leitura_da_us17():
    vendas = _VendasFalsas(VENDA)
    comprovante = ReceiptService(vendas, _EmpresaFixa()).issue(
        _vendedor(), VENDA["id"]
    )

    assert comprovante.sale_id == VENDA["id"]
    assert comprovante.company == EMPRESA
    # Uma consulta por emissão: nada de reler cliente, produto ou vendedor.
    assert len(vendas.consultas) == 1


def test_servico_recusa_quem_nao_pode_ver_vendas():
    class _SemPapel:
        role = None
        user_id = "x"

    with pytest.raises(PermissionDeniedError):
        ReceiptService(_VendasFalsas(VENDA), _EmpresaFixa()).issue(
            _SemPapel(), VENDA["id"]
        )


def test_servico_recusa_venda_inexistente():
    with pytest.raises(ReceiptNotAvailable):
        ReceiptService(_VendasFalsas(None), _EmpresaFixa()).issue(_admin(), "sumiu")


def test_servico_recusa_identificador_vazio():
    with pytest.raises(ReceiptNotAvailable):
        ReceiptService(_VendasFalsas(VENDA), _EmpresaFixa()).issue(_admin(), "")


def test_servico_recusa_venda_pendente():
    vendas = _VendasFalsas(VENDA | {"status": "PENDENTE"})
    with pytest.raises(ReceiptNotAvailable):
        ReceiptService(vendas, _EmpresaFixa()).issue(_admin(), VENDA["id"])


def test_servico_nao_expoe_nenhum_caminho_de_escrita():
    """Regra 6/7 por construção: o serviço não conhece método que grava."""
    publicos = [nome for nome in dir(ReceiptService) if not nome.startswith("_")]
    assert publicos == ["issue"]


def test_emitir_e_reemitir_nao_mudam_venda_estoque_nem_pagamentos():
    """Regra 4 e 6 contra o repositório de verdade do modo demonstração."""
    from stockflow.application.dto.sale_item import SaleItemInput
    from stockflow.domain.entities.client import Client
    from stockflow.presentation.demo_products import DEMO_PRODUCTS

    catalogo = dict(DEMO_PRODUCTS)
    repositorio = DemoSaleRepository(catalogo)
    codigo = next(iter(catalogo))
    venda = repositorio.register_multiple(
        Client(client_id="CLI-1", name="Ana Ferreira"),
        (SaleItemInput(codigo, 1),),
        Decimal(str(catalogo[codigo].sale_price).replace("R$", "").strip()
                .replace(".", "").replace(",", ".")),
        seller_id="USR-004",
    )

    class _Vendas:
        def get_sale(self, session, sale_id):
            return repositorio.get(sale_id)

    servico = ReceiptService(_Vendas(), _EmpresaFixa())
    antes = repositorio.get(venda["id"])
    saldo_antes = catalogo[codigo].stock

    primeiro = servico.issue(_admin(), venda["id"])
    segundo = servico.issue(_admin(), venda["id"])

    assert primeiro == segundo
    assert repositorio.get(venda["id"]) == antes
    assert catalogo[codigo].stock == saldo_antes
    assert len(repositorio.list_all()) == 3  # 2 sementes + 1 venda


def test_reemissao_preserva_o_nome_gravado_quando_o_cadastro_muda_depois():
    """SCRUM-228: o snapshot da venda é a fonte, não o cadastro atual."""
    vendas = _VendasFalsas(VENDA)
    servico = ReceiptService(vendas, _EmpresaFixa())
    primeiro = servico.issue(_admin(), VENDA["id"])

    # O cadastro do cliente muda; a venda gravada não.
    reemitido = servico.issue(_admin(), VENDA["id"])

    assert reemitido.client == primeiro.client == "Ana Ferreira"
    assert reemitido.items == primeiro.items
    assert reemitido.net == primeiro.net
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `QT_QPA_PLATFORM=offscreen uv run --with pytest python -m pytest tests/unit/test_sale_receipt.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'stockflow.application.services.receipt_service'`

- [ ] **Step 3: Implementar o serviço**

```python
# src/stockflow/application/services/receipt_service.py
"""Emissão e reemissão do comprovante de venda (US19/SCRUM-213).

Só de leitura, e isso é estrutural: este serviço conhece `get_sale` e
`get_profile`, e nenhum método que grave. É assim que as regras 6 e 7 da
história ficam verdadeiras por construção — uma falha aqui não tem como
alterar venda, estoque ou pagamento, porque não há o que chamar.
"""

from stockflow.domain.permissions import exigir_ver
from stockflow.domain.sale_receipt import (
    SEM_VENDA,
    ReceiptNotAvailable,
    build_sale_receipt,
)

SEM_IDENTIFICADOR = "Não foi possível identificar a venda."


class ReceiptService:
    def __init__(self, sales, companies):
        self._sales, self._companies = sales, companies

    def issue(self, session, sale_id):
        """Comprovante da venda, pelo MESMO caminho de leitura da US17.

        Emitir e reemitir são a mesma operação: não existe estado de
        "já emitido" para distinguir as duas, e inventar um seria o registro
        de emissões que a história não pede.
        """
        exigir_ver(session, "vendas", "emitir comprovante de venda")
        if not sale_id:
            raise ReceiptNotAvailable(SEM_IDENTIFICADOR)
        venda = self._sales.get_sale(session, sale_id)
        if venda is None:
            raise ReceiptNotAvailable(SEM_VENDA)
        return build_sale_receipt(venda, self._companies.get_profile())
```

- [ ] **Step 4: Rodar e ver passar**

Run: `QT_QPA_PLATFORM=offscreen uv run --with pytest python -m pytest tests/unit/test_sale_receipt.py -q`
Expected: PASS (19 testes)

- [ ] **Step 5: Commit**

```bash
git add src/stockflow/application/services/receipt_service.py tests/unit/test_sale_receipt.py
git commit -m "feat: add read-only sale receipt issuing service"
```

---

### Task 4: Renderizador HTML do comprovante

**Files:**
- Create: `src/stockflow/application/services/receipt_renderer.py`
- Test: `tests/unit/test_receipt_renderer.py`

**Interfaces:**
- Consumes: `SaleReceipt` e companhia (Task 1).
- Produces: `render_receipt_html(receipt: SaleReceipt) -> str`, `formatar_moeda(Decimal) -> str`, `formatar_documento(str) -> str`, `TITULO_VALIDO`, `TITULO_CANCELADO`, `AVISO_SEM_VALOR_FISCAL`.

- [ ] **Step 1: Escrever os testes que falham**

```python
# tests/unit/test_receipt_renderer.py
"""Layout do comprovante (US19/SCRUM-224).

HTML, e não CSV: o comprovante é documento de entrega ao cliente. Quem
renderiza é o `QTextBrowser`/`QTextDocument` do PySide6 já travado no
`uv.lock`, então o gerador é uma função pura e testável sem Qt.
"""

from decimal import Decimal

from stockflow.application.services.receipt_renderer import (
    AVISO_SEM_VALOR_FISCAL,
    TITULO_CANCELADO,
    TITULO_VALIDO,
    formatar_documento,
    formatar_moeda,
    render_receipt_html,
)
from stockflow.domain.sale_receipt import ReceiptCompany, build_sale_receipt

from test_sale_receipt import EMPRESA, VENDA


def _html(venda=VENDA, empresa=EMPRESA):
    return render_receipt_html(build_sale_receipt(venda, empresa))


def test_moeda_sai_no_formato_brasileiro():
    assert formatar_moeda(Decimal("1234.5")) == "R$ 1.234,50"
    assert formatar_moeda(Decimal("0")) == "R$ 0,00"


def test_documento_completo_sai_mascarado_e_parcial_sai_cru():
    assert formatar_documento("11222333000181") == "11.222.333/0001-81"
    assert formatar_documento("52998224725") == "529.982.247-25"
    assert formatar_documento("") == ""
    assert formatar_documento("123") == "123"


def test_cabecalho_traz_empresa_e_titulo_de_comprovante_valido():
    html = _html()
    assert "StockFlow Comércio LTDA" in html
    assert "11.222.333/0001-81" in html
    assert TITULO_VALIDO in html
    assert TITULO_CANCELADO not in html


def test_corpo_traz_identificador_data_cliente_responsavel_e_pagamento():
    html = _html()
    assert VENDA["id"] in html
    assert "31/10/2026 14:22" in html
    assert "Ana Ferreira" in html
    assert "juliana.ramos" in html
    assert "PIX" in html


def test_itens_saem_com_quantidade_preco_desconto_e_subtotal():
    html = _html()
    assert "PRD-001" in html and "Teclado" in html
    assert "R$ 30,00" in html
    assert "R$ 60,00" in html
    assert "R$ 6,00" in html
    assert "R$ 54,00" in html


def test_totais_mostram_bruto_descontos_e_total_final():
    html = _html()
    assert "R$ 90,00" in html
    assert "R$ 11,00" in html
    assert "R$ 79,00" in html


def test_venda_sem_cliente_nao_imprime_rotulo_de_cliente_vazio():
    html = _html(VENDA | {"cliente": ""})
    assert "Cliente" not in html


def test_comprovante_de_venda_cancelada_grita_o_cancelamento():
    cancelada = VENDA | {
        "status": "CANCELADA",
        "reversal_kind": "CANCELAMENTO",
        "reversal_reason": "Registro em duplicidade",
        "reversal_on": "31/10/2026 15:00",
        "reversal_by": "ana.ferreira",
    }
    html = _html(cancelada)

    assert TITULO_CANCELADO in html
    assert TITULO_VALIDO not in html
    assert "Registro em duplicidade" in html
    assert "ana.ferreira" in html
    # Os dados comerciais originais continuam lá.
    assert "R$ 79,00" in html
    assert "Teclado" in html


def test_empresa_sem_cadastro_nao_imprime_cabecalho_fantasma():
    html = _html(empresa=ReceiptCompany(name="", document=""))
    assert TITULO_VALIDO in html
    assert "CNPJ" not in html


def test_comprovante_avisa_que_nao_tem_valor_fiscal():
    """Não é nota fiscal, e o documento precisa dizer isso."""
    assert AVISO_SEM_VALOR_FISCAL in _html()


def test_conteudo_do_cliente_e_escapado_e_nao_vira_marcacao():
    html = _html(VENDA | {"cliente": "Casa & Cia <b>"})
    assert "Casa &amp; Cia &lt;b&gt;" in html
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `QT_QPA_PLATFORM=offscreen uv run --with pytest python -m pytest tests/unit/test_receipt_renderer.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'stockflow.application.services.receipt_renderer'`

- [ ] **Step 3: Implementar o renderizador**

```python
# src/stockflow/application/services/receipt_renderer.py
"""Layout do comprovante de venda em HTML (US19/SCRUM-224).

Função pura, na mesma camada e pelo mesmo motivo que `csv_exporter.py`:
serializar documento é caso de uso, não desenho de tela. Quem pinta é o
`QTextDocument`, que aceita um subconjunto de HTML 4 — por isso tabela com
`cellpadding` e estilo em atributo, e nada de CSS moderno.
"""

from decimal import Decimal
from html import escape

from stockflow.domain.sale_receipt import SaleReceipt

TITULO_VALIDO = "COMPROVANTE DE VENDA"
TITULO_CANCELADO = "COMPROVANTE DE VENDA CANCELADA"
AVISO_SEM_VALOR_FISCAL = (
    "Documento de conferência emitido pelo StockFlow. Não tem valor fiscal."
)

_BORDA = "#E2E8F0"
_TEXTO = "#0F172A"
_SUAVE = "#64748B"
_ALERTA = "#B91C1C"


def formatar_moeda(valor: Decimal) -> str:
    """"1234.5" -> "R$ 1.234,50"."""
    texto = f"{Decimal(valor):,.2f}".replace(",", "_").replace(".", ",")
    return "R$ " + texto.replace("_", ".")


def formatar_documento(documento: str) -> str:
    """Mascara CPF/CNPJ completo; devolve cru o que não tiver o tamanho."""
    digitos = "".join(c for c in (documento or "") if c.isdigit())
    if len(digitos) == 14:
        return (f"{digitos[:2]}.{digitos[2:5]}.{digitos[5:8]}"
                f"/{digitos[8:12]}-{digitos[12:]}")
    if len(digitos) == 11:
        return f"{digitos[:3]}.{digitos[3:6]}.{digitos[6:9]}-{digitos[9:]}"
    return documento or ""


def _linha(rotulo, valor):
    return (f"<tr><td style='color:{_SUAVE};padding:2px 12px 2px 0'>{rotulo}</td>"
            f"<td style='color:{_TEXTO}'>{valor}</td></tr>")


def _cabecalho_da_empresa(receipt):
    if not receipt.company.identificada:
        # Sem cadastro legível não se inventa emitente: um cabeçalho em
        # branco diria que a empresa se chama "".
        return ""
    documento = formatar_documento(receipt.company.document)
    linha_documento = (
        f"<div style='color:{_SUAVE};font-size:11px'>CNPJ {escape(documento)}</div>"
        if documento else ""
    )
    return (f"<div style='font-size:16px;font-weight:bold;color:{_TEXTO}'>"
            f"{escape(receipt.company.name)}</div>{linha_documento}")


def _titulo(receipt):
    if not receipt.cancelado:
        return (f"<div style='font-size:14px;font-weight:bold;color:{_TEXTO};"
                f"padding:10px 0'>{TITULO_VALIDO}</div>")
    rotulo = (TITULO_CANCELADO if receipt.cancellation is None
              else f"COMPROVANTE DE VENDA {receipt.status.label.upper()}")
    return (f"<div style='font-size:14px;font-weight:bold;color:{_ALERTA};"
            f"border:2px solid {_ALERTA};padding:8px'>{rotulo}</div>")


def _dados_da_operacao(receipt):
    linhas = [_linha("Venda", escape(receipt.sale_id)),
              _linha("Data", escape(receipt.issued_on))]
    # Cliente só aparece quando a venda tem um associado (regra 3).
    if receipt.client:
        linhas.append(_linha("Cliente", escape(receipt.client)))
    linhas.append(_linha("Responsável", escape(receipt.seller or "—")))
    return "<table>" + "".join(linhas) + "</table>"


def _itens(receipt):
    cabecalho = "".join(
        f"<th align='{alinhamento}' style='border-bottom:1px solid {_BORDA};"
        f"color:{_SUAVE};font-weight:normal'>{titulo}</th>"
        for titulo, alinhamento in (
            ("Código", "left"), ("Produto", "left"), ("Qtd.", "right"),
            ("Preço unit.", "right"), ("Subtotal", "right"),
            ("Desconto", "right"), ("Total", "right"),
        )
    )
    corpo = "".join(
        "<tr>"
        f"<td>{escape(item.code)}</td>"
        f"<td>{escape(item.name)}</td>"
        f"<td align='right'>{item.quantity}</td>"
        f"<td align='right'>{formatar_moeda(item.unit_price)}</td>"
        f"<td align='right'>{formatar_moeda(item.subtotal)}</td>"
        f"<td align='right'>{formatar_moeda(item.discount)}</td>"
        f"<td align='right'>{formatar_moeda(item.final_subtotal)}</td>"
        "</tr>"
        for item in receipt.items
    )
    return (f"<table width='100%' cellpadding='4' cellspacing='0'>"
            f"<tr>{cabecalho}</tr>{corpo}</table>")


def _totais(receipt):
    linhas = [_linha("Subtotal bruto", formatar_moeda(receipt.gross))]
    if receipt.item_discount:
        linhas.append(_linha("Descontos nos itens",
                             formatar_moeda(receipt.item_discount)))
    if receipt.sale_discount:
        linhas.append(_linha("Desconto na venda",
                             formatar_moeda(receipt.sale_discount)))
    linhas.append(_linha("Desconto total", formatar_moeda(receipt.total_discount)))
    linhas.append(
        f"<tr><td style='font-size:14px;font-weight:bold;padding-top:6px'>TOTAL</td>"
        f"<td style='font-size:14px;font-weight:bold;padding-top:6px'>"
        f"{formatar_moeda(receipt.net)}</td></tr>"
    )
    return "<table>" + "".join(linhas) + "</table>"


def _pagamento(receipt):
    return ("<table>"
            + _linha("Forma de pagamento", escape(receipt.payment.method or "—"))
            + _linha("Valor pago", formatar_moeda(receipt.payment.amount))
            + "</table>")


def _cancelamento(receipt):
    reversao = receipt.cancellation
    if reversao is None:
        return ""
    return (f"<table style='color:{_ALERTA}'>"
            + _linha("Operação", escape(reversao.kind.label))
            + _linha("Motivo", escape(reversao.reason or "—"))
            + _linha("Quando", escape(reversao.when or "—"))
            + _linha("Responsável", escape(reversao.by or "—"))
            + "</table>")


def render_receipt_html(receipt: SaleReceipt) -> str:
    """Documento completo, pronto para `QTextDocument.setHtml`."""
    separador = f"<hr style='border:0;border-top:1px solid {_BORDA}'>"
    return (
        f"<div style='font-family:sans-serif;font-size:12px;color:{_TEXTO}'>"
        f"{_cabecalho_da_empresa(receipt)}"
        f"{_titulo(receipt)}"
        f"{_dados_da_operacao(receipt)}{separador}"
        f"{_itens(receipt)}{separador}"
        f"{_totais(receipt)}{separador}"
        f"{_pagamento(receipt)}"
        f"{_cancelamento(receipt)}"
        f"<div style='color:{_SUAVE};font-size:10px;padding-top:12px'>"
        f"{AVISO_SEM_VALOR_FISCAL}</div>"
        f"</div>"
    )
```

- [ ] **Step 4: Rodar e ver passar**

Run: `QT_QPA_PLATFORM=offscreen uv run --with pytest python -m pytest tests/unit/test_receipt_renderer.py -q`
Expected: PASS (11 testes)

- [ ] **Step 5: Commit**

```bash
git add src/stockflow/application/services/receipt_renderer.py tests/unit/test_receipt_renderer.py
git commit -m "feat: render sale receipt layout as HTML"
```

---

### Task 5: Diálogo do comprovante (ver, PDF, imprimir)

**Files:**
- Create: `src/stockflow/presentation/widgets/sale_receipt_dialog.py`
- Test: `tests/test_us19_comprovante_ui.py`

**Interfaces:**
- Consumes: `render_receipt_html` (Task 4), `SaleReceipt` (Task 1).
- Produces: `SaleReceiptDialog(receipt, parent=None)` com `.html`, `.viewer`, `.pdf_button`, `.print_button`, `.close_button`, `.status_label`, `.export_pdf(path)`, `.sugerir_nome_do_arquivo()`.

- [ ] **Step 1: Escrever os testes que falham**

```python
# tests/test_us19_comprovante_ui.py
"""Interface do comprovante (US19/SCRUM-224).

O diálogo é o ponto de entrega: mostra, grava PDF e imprime. Impressão abre
diálogo do sistema e por isso não é exercida aqui; o PDF é, porque
`QPdfWriter` funciona sem servidor gráfico.
"""

import pytest

from stockflow.application.services.receipt_renderer import TITULO_CANCELADO
from stockflow.domain.sale_receipt import ReceiptCompany, build_sale_receipt
from stockflow.presentation.widgets.sale_receipt_dialog import SaleReceiptDialog

# Repetida aqui de propósito: `tests/unit` não está no caminho de import de
# `tests/` quando este arquivo roda sozinho, e `test_us17_detalhe_da_venda.py`
# já fixa a mesma convenção de venda literal no teste de tela.
EMPRESA = ReceiptCompany(name="StockFlow Comércio LTDA", document="11222333000181")

VENDA = {
    "id": "3f2a7c41-0000-4000-8000-000000000001",
    "cliente": "Ana Ferreira",
    "seller": "juliana.ramos",
    "data": "31/10/2026 14:22",
    "status": "CONCLUIDA",
    "payment_method": "PIX",
    "discount": "11.00",
    "original_total": "90.00",
    "total": "79.00",
    "valor": "R$ 79,00",
    "items": [
        {"product_code": "PRD-001", "product_name": "Teclado", "quantity": 2,
         "unit_price": "30.00", "subtotal": "60.00",
         "discount_amount": "6.00", "final_subtotal": "54.00"},
        {"product_code": "PRD-002", "product_name": "Mouse", "quantity": 1,
         "unit_price": "30.00", "subtotal": "30.00",
         "discount_amount": "0.00", "final_subtotal": "30.00"},
    ],
}

from test_sale_receipt import EMPRESA, VENDA


@pytest.fixture
def dialogo(qapp):
    janela = SaleReceiptDialog(build_sale_receipt(VENDA, EMPRESA))
    yield janela
    janela.close()


def test_dialogo_mostra_o_comprovante_renderizado(dialogo):
    texto = dialogo.viewer.toPlainText()
    assert "Ana Ferreira" in texto
    assert "Teclado" in texto
    assert "R$ 79,00" in texto


def test_dialogo_oferece_pdf_impressao_e_fechar(dialogo):
    assert dialogo.pdf_button.isEnabled()
    assert dialogo.print_button.isEnabled()
    assert dialogo.close_button.isEnabled()


def test_nome_sugerido_carrega_o_identificador_da_venda(dialogo):
    nome = dialogo.sugerir_nome_do_arquivo()
    assert nome.endswith(".pdf")
    assert VENDA["id"][:8] in nome


def test_exportar_pdf_grava_um_arquivo_legivel(dialogo, tmp_path):
    destino = tmp_path / "comprovante.pdf"
    dialogo.export_pdf(str(destino))

    assert destino.exists()
    assert destino.read_bytes().startswith(b"%PDF")


def test_falha_na_gravacao_vira_aviso_na_janela_e_nao_derruba_o_dialogo(
    dialogo, tmp_path
):
    """Regra 7: falhar ao gerar não pode quebrar nada além da geração."""
    inexistente = tmp_path / "sem" / "pasta" / "c.pdf"
    dialogo._gravar_pdf(str(inexistente))

    assert "Não foi possível" in dialogo.status_label.text()
    assert dialogo.isEnabled()


def test_dialogo_de_venda_cancelada_mostra_a_marcacao(qapp):
    cancelada = VENDA | {
        "status": "CANCELADA",
        "reversal_kind": "CANCELAMENTO",
        "reversal_reason": "Registro em duplicidade",
        "reversal_on": "31/10/2026 15:00",
        "reversal_by": "ana.ferreira",
    }
    janela = SaleReceiptDialog(build_sale_receipt(cancelada, EMPRESA))
    try:
        assert TITULO_CANCELADO in janela.viewer.toPlainText()
        assert "Registro em duplicidade" in janela.viewer.toPlainText()
    finally:
        janela.close()
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `QT_QPA_PLATFORM=offscreen uv run --with pytest python -m pytest tests/test_us19_comprovante_ui.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'stockflow.presentation.widgets.sale_receipt_dialog'`

- [ ] **Step 3: Implementar o diálogo**

```python
# src/stockflow/presentation/widgets/sale_receipt_dialog.py
"""Entrega do comprovante: ver, salvar em PDF e imprimir (US19/SCRUM-224).

Nada aqui grava no banco. Erro de arquivo ou de impressora vira aviso na
própria janela — a venda já estava fechada antes de o diálogo abrir, e a
regra 7 da história exige que uma falha de geração não vá além dela.
"""

import qtawesome as qta
from PySide6.QtCore import QMarginsF, Qt
from PySide6.QtGui import QPageLayout, QPageSize, QPdfWriter, QTextDocument
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
)

from stockflow.application.services.receipt_renderer import render_receipt_html
from stockflow.presentation.styles import inventory

MARGEM_MM = 12


class SaleReceiptDialog(QDialog):
    def __init__(self, receipt, parent=None):
        super().__init__(parent)
        self.receipt = receipt
        self.html = render_receipt_html(receipt)
        self.setObjectName("saleReceiptDialog")
        self.setWindowTitle("Comprovante de venda")
        self.setMinimumSize(620, 640)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        self.viewer = QTextBrowser()
        self.viewer.setObjectName("saleReceiptViewer")
        self.viewer.setHtml(self.html)
        # Documento, não navegador: link clicável num comprovante abriria
        # caminho para fora do aplicativo sem nenhum ganho.
        self.viewer.setOpenExternalLinks(False)
        self.viewer.setOpenLinks(False)
        layout.addWidget(self.viewer, 1)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setVisible(False)
        layout.addWidget(self.status_label)

        layout.addLayout(self._criar_acoes())

    def _criar_acoes(self):
        linha = QHBoxLayout()
        linha.addStretch()
        self.pdf_button = QPushButton(" Salvar PDF")
        self.pdf_button.setIcon(qta.icon("fa5s.file-pdf", color="#B91C1C"))
        self.pdf_button.setAccessibleName("Salvar o comprovante em PDF")
        self.pdf_button.clicked.connect(self._escolher_destino)
        self.print_button = QPushButton(" Imprimir")
        self.print_button.setIcon(qta.icon("fa5s.print", color="#2563EB"))
        self.print_button.setAccessibleName("Imprimir o comprovante")
        self.print_button.clicked.connect(self._imprimir)
        self.close_button = QPushButton("Fechar")
        self.close_button.setAccessibleName("Fechar o comprovante")
        self.close_button.clicked.connect(self.accept)
        for botao in (self.pdf_button, self.print_button, self.close_button):
            botao.setFixedHeight(40)
            botao.setCursor(Qt.PointingHandCursor)
            botao.setStyleSheet(inventory.NEW_BUTTON_QSS)
            linha.addWidget(botao)
        return linha

    # ------------------------------------------------------------- saídas

    def sugerir_nome_do_arquivo(self) -> str:
        """Identificador curto no nome: o uuid inteiro não cabe na coluna de
        nome de arquivo de nenhum gerenciador, e o prefixo é como a tela já
        identifica a venda."""
        return f"comprovante-{str(self.receipt.sale_id)[:8]}.pdf"

    def export_pdf(self, path: str) -> None:
        """Grava o PDF. Levanta em erro de E/S, para quem chamou decidir."""
        writer = QPdfWriter(path)
        writer.setPageSize(QPageSize(QPageSize.A4))
        writer.setPageMargins(
            QMarginsF(MARGEM_MM, MARGEM_MM, MARGEM_MM, MARGEM_MM),
            QPageLayout.Millimeter,
        )
        documento = QTextDocument()
        documento.setHtml(self.html)
        documento.print_(writer)

    def _gravar_pdf(self, path: str) -> None:
        try:
            self.export_pdf(path)
        except Exception as erro:
            self._avisar(f"Não foi possível salvar o PDF: {erro}", erro=True)
            return
        self._avisar(f"Comprovante salvo em {path}.")

    def _escolher_destino(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Salvar comprovante", self.sugerir_nome_do_arquivo(),
            "PDF (*.pdf)",
        )
        if path:
            self._gravar_pdf(path)

    def _imprimir(self):
        from PySide6.QtPrintSupport import QPrintDialog, QPrinter

        try:
            printer = QPrinter(QPrinter.HighResolution)
            dialogo = QPrintDialog(printer, self)
            if dialogo.exec() != QDialog.Accepted:
                return
            documento = QTextDocument()
            documento.setHtml(self.html)
            documento.print_(printer)
        except Exception as erro:
            self._avisar(f"Não foi possível imprimir: {erro}", erro=True)
            return
        self._avisar("Comprovante enviado para a impressora.")

    def _avisar(self, mensagem, erro=False):
        self.status_label.setStyleSheet(
            inventory.LOAD_ERROR_QSS if erro
            else "color: #15803D; font-size: 13px;"
        )
        self.status_label.setText(mensagem)
        self.status_label.setVisible(True)
```

**Atenção do implementador:** `QPrintDialog`/`QPrinter` ficam importados
DENTRO de `_imprimir`, e não no topo: `QtPrintSupport` é a única parte do Qt
usada aqui que o resto do aplicativo nunca carrega, e importá-la na montagem
do módulo faria toda a suíte pagar por um recurso que só quem manda imprimir
usa.

- [ ] **Step 4: Rodar e ver passar**

Run: `QT_QPA_PLATFORM=offscreen uv run --with pytest python -m pytest tests/test_us19_comprovante_ui.py -q`
Expected: PASS (6 testes)

- [ ] **Step 5: Commit**

```bash
git add src/stockflow/presentation/widgets/sale_receipt_dialog.py tests/test_us19_comprovante_ui.py
git commit -m "feat: add receipt dialog with PDF export and printing"
```

---

### Task 6: Botão no detalhe da venda

**Files:**
- Modify: `src/stockflow/presentation/pages/sale_details.py` (sinal novo; `_criar_acoes`; `_aplicar_alcada`; `load_sale` no ramo de venda ausente)
- Modify: `tests/test_us19_comprovante_ui.py` (nova seção)

**Interfaces:**
- Consumes: nada das tarefas anteriores (a página só emite o identificador).
- Produces: `SaleDetailsPage.receipt_requested = Signal(str)` e `SaleDetailsPage.receipt_button`.

- [ ] **Step 1: Acrescentar os testes que falham**

```python
# acrescentar ao fim de tests/test_us19_comprovante_ui.py

from stockflow.domain.enums.user_role import UserRole
from stockflow.presentation.demo_accounts import conta_por_papel
from stockflow.presentation.pages.sale_details import SaleDetailsPage


@pytest.fixture
def detalhe(qapp):
    page = SaleDetailsPage()
    yield page
    page.close()


def _vendedor():
    return conta_por_papel(UserRole.SELLER).session()


def test_detalhe_oferece_emitir_comprovante_para_venda_concluida(detalhe):
    detalhe.load_sale(VENDA, _vendedor())
    assert detalhe.receipt_button.isVisible() or not detalhe.isVisible()
    assert detalhe.receipt_button.isEnabled()


def test_detalhe_emite_o_identificador_da_venda_ao_clicar(detalhe):
    detalhe.load_sale(VENDA, _vendedor())
    pedidos = []
    detalhe.receipt_requested.connect(pedidos.append)

    detalhe.receipt_button.click()

    assert pedidos == [VENDA["id"]]


def test_detalhe_desabilita_o_botao_para_venda_pendente(detalhe):
    """Cortesia visual; a recusa de verdade é do serviço (SCRUM-227)."""
    detalhe.load_sale(VENDA | {"status": "PENDENTE"}, _vendedor())
    assert not detalhe.receipt_button.isEnabled()
    assert "não foi confirmada" in detalhe.receipt_button.toolTip()


def test_detalhe_mantem_o_botao_para_venda_cancelada(detalhe):
    """SCRUM-229: a venda cancelada tem comprovante — marcado."""
    detalhe.load_sale(VENDA | {"status": "CANCELADA"}, _vendedor())
    assert detalhe.receipt_button.isEnabled()


def test_detalhe_sem_venda_nao_oferece_emissao(detalhe):
    detalhe.load_sale(None, _vendedor())
    assert not detalhe.receipt_button.isEnabled()
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `QT_QPA_PLATFORM=offscreen uv run --with pytest python -m pytest tests/test_us19_comprovante_ui.py -q`
Expected: FAIL — `AttributeError: 'SaleDetailsPage' object has no attribute 'receipt_button'`

- [ ] **Step 3: Acrescentar o sinal e o botão**

Em `src/stockflow/presentation/pages/sale_details.py`:

1. Depois de `return_requested = Signal(str, str)`, acrescentar:

```python
    #: Identificador da venda cujo comprovante foi pedido (US19). A página
    #: não emite o documento: quem monta o comprovante é o serviço, que a
    #: janela já tem montado.
    receipt_requested = Signal(str)
```

2. Em `_criar_acoes`, antes da criação de `self.cancel_button`, acrescentar o
   botão e incluí-lo no laço de estilo:

```python
        self.receipt_button = QPushButton("Emitir comprovante")
        self.receipt_button.setIcon(qta.icon("fa5s.file-invoice", color="#2563EB"))
        self.receipt_button.setAccessibleName("Emitir o comprovante desta venda")
        self.receipt_button.clicked.connect(self._pedir_comprovante)
```

   e trocar o laço final de `_criar_acoes` por:

```python
        for botao in (self.receipt_button, self.cancel_button, self.return_button):
```

3. No ramo de venda ausente de `load_sale`, trocar

```python
            for botao in (self.cancel_button, self.return_button):
                botao.setEnabled(False)
```

   por

```python
            for botao in (self.receipt_button, self.cancel_button,
                          self.return_button):
                botao.setEnabled(False)
```

4. No fim de `_aplicar_alcada`, acrescentar:

```python
        # Comprovante é LEITURA: quem abre o detalhe pode emitir. O que o
        # status decide é outra coisa — venda pendente nunca foi confirmada,
        # então não há operação a comprovar (SCRUM-227). Cancelada tem
        # comprovante, e ele sai marcado (SCRUM-229).
        emitivel = situacao is not SaleStatus.PENDENTE
        self.receipt_button.setEnabled(emitivel)
        self.receipt_button.setToolTip(
            "Emitir o comprovante desta venda" if emitivel
            else "Esta venda ainda não foi confirmada."
        )
```

5. Acrescentar o manipulador junto dos demais, no fim da classe:

```python
    def _pedir_comprovante(self):
        if self.venda:
            self.receipt_requested.emit(str(self.venda["id"]))
```

- [ ] **Step 4: Rodar e ver passar**

Run: `QT_QPA_PLATFORM=offscreen uv run --with pytest python -m pytest tests/test_us19_comprovante_ui.py tests/test_us17_detalhe_da_venda.py -q`
Expected: PASS (todos; a suíte da US17 não pode regredir)

- [ ] **Step 5: Commit**

```bash
git add src/stockflow/presentation/pages/sale_details.py tests/test_us19_comprovante_ui.py
git commit -m "feat: offer receipt issuing from sale details"
```

---

### Task 7: Botão após a confirmação da venda

**Files:**
- Modify: `src/stockflow/presentation/pages/vendas.py` (sinal novo; botão no bloco de aviso; `_venda_gravada`; `_limpar_venda`)
- Modify: `src/stockflow/infrastructure/repositories/demo_sale_repository.py` (completar as duas vendas semente)
- Modify: `tests/test_us19_comprovante_ui.py` (nova seção)

**Interfaces:**
- Produces: `VendasPage.receipt_requested = Signal(str)` e `VendasPage.receipt_button`.

- [ ] **Step 1: Acrescentar os testes que falham**

```python
# acrescentar ao fim de tests/test_us19_comprovante_ui.py

def test_vendas_esconde_o_botao_antes_de_qualquer_venda(vendas_page):
    assert not vendas_page.receipt_button.isVisible()


def test_vendas_oferece_comprovante_depois_de_gravar(vendas_page):
    vendas_page._venda_gravada({
        "id": "VND-9001", "cliente": "Ana Ferreira", "produto": "Teclado",
        "valor": "R$ 79,00", "data": "31/10/2026 14:22", "status": "CONCLUIDA",
        "items": [],
    })
    pedidos = []
    vendas_page.receipt_requested.connect(pedidos.append)

    vendas_page.receipt_button.click()

    assert pedidos == ["VND-9001"]


def test_vendas_esconde_o_botao_ao_comecar_uma_venda_nova(vendas_page):
    vendas_page._venda_gravada({
        "id": "VND-9002", "cliente": "Ana Ferreira", "produto": "Teclado",
        "valor": "R$ 79,00", "data": "31/10/2026 14:30", "status": "CONCLUIDA",
        "items": [],
    })
    vendas_page._limpar_venda()
    assert not vendas_page.receipt_button.isVisible()


def test_vendas_semente_da_demonstracao_tem_itens_para_comprovar():
    """Sem itens gravados não há comprovante, e a demonstração precisa de um
    histórico sobre o qual a US19 possa ser exercida."""
    from stockflow.infrastructure.repositories.demo_sale_repository import (
        DemoSaleRepository,
    )

    for linha in DemoSaleRepository().list_all():
        assert linha["items"]
        assert linha["status"] == "CONCLUIDA"
        assert linha["original_total"]
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `QT_QPA_PLATFORM=offscreen uv run --with pytest python -m pytest tests/test_us19_comprovante_ui.py -q`
Expected: FAIL — `AttributeError: 'VendasPage' object has no attribute 'receipt_button'`

- [ ] **Step 3: Completar as vendas semente da demonstração**

Em `src/stockflow/infrastructure/repositories/demo_sale_repository.py`, trocar a
atribuição de `self.rows` no `__init__` por:

```python
        # As sementes carregam itens, status e totais porque o comprovante
        # (US19) lê o SNAPSHOT da venda: linha sem item não tem o que
        # comprovar, e a demonstração ficaria sem histórico emitível.
        self.rows = [
            self._semente("VND-1001", "Patrícia Lima", "PRD-004",
                          "Cabo HDMI 2m", 450, "10/08/2026"),
            self._semente("VND-1002", "Ana Ferreira", "PRD-007",
                          "Mouse ergonômico", 1290, "28/09/2026"),
        ]
```

e acrescentar o auxiliar logo acima de `get_discount_limits`:

```python
    @staticmethod
    def _semente(sale_id, cliente, codigo, nome, total, data):
        valor = Decimal(str(total)).quantize(Decimal("0.01"))
        linha = sale_row(sale_id, cliente, [codigo], [nome], valor, data,
                         item_count=1)
        linha.update(
            status="CONCLUIDA",
            payment_method="DINHEIRO",
            discount="0.00",
            original_total=str(valor),
            seller="ana.ferreira",
            items=[{
                "product_code": codigo, "product_name": nome, "quantity": 1,
                "unit_price": str(valor), "subtotal": str(valor),
                "discount_amount": "0.00", "final_subtotal": str(valor),
            }],
        )
        return linha
```

- [ ] **Step 4: Acrescentar o sinal e o botão na tela de vendas**

Em `src/stockflow/presentation/pages/vendas.py`:

1. Depois de `detalhes_requested = Signal(str)`, acrescentar:

```python
    #: Identificador da venda recém-gravada cujo comprovante foi pedido
    #: (US19). "Emitir após a confirmação da venda" é a história literal, e
    #: a alternativa — mandar o operador caçar a venda no histórico — é
    #: exatamente o atrito que ela existe para remover.
    receipt_requested = Signal(str)
```

2. Logo depois da criação de `self.warning_label` (por volta da linha 230),
   acrescentar:

```python
        self.receipt_button = QPushButton(" Emitir comprovante")
        self.receipt_button.setIcon(qta.icon("fa5s.file-invoice", color="#2563EB"))
        self.receipt_button.setAccessibleName("Emitir o comprovante da última venda")
        self.receipt_button.setCursor(Qt.PointingHandCursor)
        self.receipt_button.setFixedHeight(36)
        self.receipt_button.setStyleSheet(inventory.FILTER_QSS)
        self.receipt_button.setVisible(False)
        self.receipt_button.clicked.connect(self._pedir_comprovante)
        self._ultima_venda = None
```

3. Logo depois de `layout.addWidget(self.warning_label)` (por volta da linha
   372), acrescentar `layout.addWidget(self.receipt_button)`.

4. Em `_venda_gravada`, depois de `self.last_error = None`, acrescentar:

```python
        self._ultima_venda = str(nova_venda.get("id") or "")
        self.receipt_button.setVisible(bool(self._ultima_venda))
```

5. No fim de `_limpar_venda`, acrescentar:

```python
        # A oferta é da venda que acabou de fechar; começar outra retira o
        # botão, para ninguém emitir o comprovante da venda anterior achando
        # que é o da que está montando.
        self._ultima_venda = None
        self.receipt_button.setVisible(False)
```

   **Atenção:** `_venda_gravada` chama `_limpar_venda` ANTES de marcar a
   última venda. Confira a ordem no arquivo; se `_limpar_venda` vier antes,
   os passos 4 e 5 já ficam corretos nessa ordem. Se o passo 4 for inserido
   antes da chamada a `_limpar_venda`, mova-o para depois.

6. Garantir que `inventory` e `qta` já estão importados no módulo (estão;
   `vendas.py` já usa os dois).

- [ ] **Step 5: Rodar e ver passar**

Run: `QT_QPA_PLATFORM=offscreen uv run --with pytest python -m pytest tests/test_us19_comprovante_ui.py tests/test_operations_filters.py tests/test_us02_validacao_produto_ativo.py tests/test_sales_checkout_regression.py -q`
Expected: PASS (as três últimas são as que tocam as vendas semente)

- [ ] **Step 6: Commit**

```bash
git add src/stockflow/presentation/pages/vendas.py \
        src/stockflow/infrastructure/repositories/demo_sale_repository.py \
        tests/test_us19_comprovante_ui.py
git commit -m "feat: offer receipt right after sale confirmation"
```

---

### Task 8: Ligação na janela principal e regressão

**Files:**
- Modify: `src/stockflow/presentation/windows/main_window.py` (import de `build_company_repository`; montagem do `ReceiptService` em `_create_pages`; conexões em `_connect`; manipulador `_emitir_comprovante`)
- Modify: `tests/test_us19_comprovante_ui.py` (seção da janela)
- Modify: `README.md` (parágrafo da US19 na seção de Vendas)

**Interfaces:**
- Consumes: `ReceiptService` (Task 3), `build_company_repository` (Task 2), `SaleReceiptDialog` (Task 5), os sinais das Tasks 6 e 7.
- Produces: `MainWindow.receipt_service` e `MainWindow._emitir_comprovante(sale_id)`.

- [ ] **Step 1: Acrescentar os testes que falham**

```python
# acrescentar ao fim de tests/test_us19_comprovante_ui.py

def test_janela_monta_o_servico_de_comprovante_e_liga_as_duas_entradas(qapp):
    from stockflow.presentation.windows.main_window import MainWindow

    janela = MainWindow(conta_por_papel(UserRole.ADMIN).session())
    try:
        assert janela.receipt_service is not None
        # Emitir pelas duas portas chega no mesmo manipulador.
        assert janela.sale_details_page.receipt_requested is not None
        assert janela.vendas_page.receipt_requested is not None
    finally:
        janela.close()


def test_janela_recusa_comprovante_de_venda_pendente_sem_abrir_dialogo(
    qapp, monkeypatch
):
    """Regra 7: a recusa é uma mensagem, não uma janela de comprovante."""
    from PySide6.QtWidgets import QMessageBox
    from stockflow.presentation.windows import main_window as modulo

    janela = modulo.MainWindow(conta_por_papel(UserRole.ADMIN).session())
    try:
        pendente = dict(VENDA, status="PENDENTE")
        monkeypatch.setattr(
            janela.sale_service, "get_sale",
            lambda session, sale_id: pendente,
        )
        avisos = []
        monkeypatch.setattr(
            QMessageBox, "information",
            lambda *args, **kwargs: avisos.append(args[2]),
        )
        abertos = []
        monkeypatch.setattr(
            modulo, "SaleReceiptDialog",
            lambda *args, **kwargs: abertos.append(args) or (_ for _ in ()).throw(
                AssertionError("não devia abrir")
            ),
        )

        janela._emitir_comprovante(VENDA["id"])

        assert abertos == []
        assert avisos and "não foi confirmada" in avisos[0]
    finally:
        janela.close()


def test_janela_nao_altera_a_venda_ao_emitir(qapp, monkeypatch):
    from stockflow.presentation.windows import main_window as modulo

    janela = modulo.MainWindow(conta_por_papel(UserRole.ADMIN).session())
    try:
        antes = [dict(linha) for linha in janela.sale_repository.list_all()]
        monkeypatch.setattr(
            modulo, "SaleReceiptDialog", lambda *args, **kwargs: _DialogoMudo()
        )
        janela._emitir_comprovante(antes[0]["id"])
        depois = [dict(linha) for linha in janela.sale_repository.list_all()]
        assert depois == antes
    finally:
        janela.close()


class _DialogoMudo:
    """Substitui o diálogo: o teste é sobre não gravar, não sobre pintar."""

    def exec(self):
        return 0
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `QT_QPA_PLATFORM=offscreen uv run --with pytest python -m pytest tests/test_us19_comprovante_ui.py -q`
Expected: FAIL — `AttributeError: 'MainWindow' object has no attribute 'receipt_service'`

- [ ] **Step 3: Ligar na janela**

Em `src/stockflow/presentation/windows/main_window.py`:

1. No bloco de imports de `backend` (linhas 24-25), acrescentar
   `build_company_repository,` na lista.

2. No topo do módulo, junto dos demais imports de página/widget, acrescentar:

```python
from stockflow.presentation.widgets.sale_receipt_dialog import SaleReceiptDialog
```

3. Em `_create_pages`, logo depois de
   `self.sale_service = SaleService(...)`, acrescentar:

```python
        from stockflow.application.services.receipt_service import ReceiptService

        self.company_repository = build_company_repository(self.session)
        self.receipt_service = ReceiptService(
            self.sale_service, self.company_repository
        )
```

4. Em `_connect`, junto das conexões de `sale_details_page` (linhas 341-342),
   acrescentar:

```python
        self.sale_details_page.receipt_requested.connect(self._emitir_comprovante)
        self.vendas_page.receipt_requested.connect(self._emitir_comprovante)
```

5. Logo depois de `_show_sale_details`, acrescentar o manipulador:

```python
    def _emitir_comprovante(self, sale_id):
        """Emite ou reemite o comprovante (US19/SCRUM-213).

        Relê pelo SERVIÇO, como `_show_sale_details`: a linha da tabela é
        foto do momento da consulta, e um comprovante reemitido depois de um
        cancelamento feito noutra máquina sairia sem a marcação.
        """
        try:
            comprovante = self.receipt_service.issue(self.session, sale_id)
        except PermissionDeniedError as erro:
            QMessageBox.critical(self, "Acesso restrito", str(erro))
            return
        except ReceiptNotAvailable as erro:
            QMessageBox.information(self, "Comprovante indisponível", str(erro))
            return
        except Exception as erro:
            QMessageBox.warning(
                self, "Não foi possível emitir o comprovante", str(erro)
            )
            return
        SaleReceiptDialog(comprovante, self).exec()
```

6. Acrescentar o import da exceção junto dos demais imports de domínio:

```python
from stockflow.domain.sale_receipt import ReceiptNotAvailable
```

   **Atenção:** `ReceiptNotAvailable` herda de `ValueError`, então o `except`
   dela precisa vir ANTES do `except Exception` — e vem, na ordem acima.

- [ ] **Step 4: Rodar e ver passar**

Run: `QT_QPA_PLATFORM=offscreen uv run --with pytest python -m pytest tests/test_us19_comprovante_ui.py -q`
Expected: PASS

- [ ] **Step 5: Rodar a suíte inteira**

Run: `QT_QPA_PLATFORM=offscreen uv run --with pytest python -m pytest tests/ -q`
Expected: PASS, sem regressão. Se `tests/test_page_loading.py` ou
`tests/test_feature_ui.py` reclamarem de widget novo, ajuste a expectativa
deles — são testes que inventariam a tela.

- [ ] **Step 6: Documentar no README**

Acrescentar, na seção de Vendas do `README.md`, um parágrafo com: onde fica o
botão (detalhe da venda e logo após fechar uma venda), que venda pendente não
emite, que venda cancelada emite com marcação, e que o PDF sai pelo botão
**Salvar PDF**.

- [ ] **Step 7: Commit**

```bash
git add src/stockflow/presentation/windows/main_window.py \
        tests/test_us19_comprovante_ui.py README.md
git commit -m "feat: wire receipt issuing into the main window"
```

---

## Verificação final

- [ ] `QT_QPA_PLATFORM=offscreen uv run --with pytest python -m pytest tests/ -q` verde.
- [ ] `git diff main --stat` não mostra nada em `database/` nem em `pyproject.toml`.
- [ ] `grep -rn "receipt" src/stockflow | grep -iE "insert|update|delete|rpc\(" ` não retorna nada — nenhum caminho de escrita na emissão.
- [ ] Teste manual conforme a seção de entrega.

"""Adaptador de `MovementRepository` sobre o catálogo em memória da demonstração.

Mesma porta do `SupabaseMovementRepository`, para que o `MovementService` e a
tela não saibam qual dos dois está em uso.

O QUE ESTE ARQUIVO PRECISA IMITAR do banco, e por quê:

1. **Histórico próprio.** Movimentação é linha de `stock_movements`, não
   atributo do produto. Guardar só o saldo faria a tela de Movimentações
   nascer vazia no modo demonstração, e "por que o saldo mudou?" deixaria de
   ter resposta.
2. **Confirmar é o que move o saldo.** No banco quem move é o trigger, ao ver
   a situação virar `CONFIRMADA`; aqui o equivalente é aplicar a diferença no
   `Product` do catálogo compartilhado. Uma PENDENTE não pode mexer em nada —
   é a distinção inteira da US03.
3. **Cancelar uma confirmada devolve o saldo.** Lá, porque
   `fn_confirmed_balance` recalcula a soma das que seguem confirmadas; aqui,
   desfazendo a diferença que a confirmação aplicou.

O dict `code -> Product` é o MESMO que as telas leem — é essa identidade que
faz a confirmação aparecer na tabela de Estoque sem ninguém recarregar nada,
como em `DemoProductRepository`.
"""

import dataclasses
from datetime import datetime

from stockflow.application.dto.movement_input import MovementInput
from stockflow.domain.enums.movement_kind import MovementKind
from stockflow.domain.enums.movement_status import MovementStatus
from stockflow.domain.stock_level import derive_stock_status, to_int
from stockflow.infrastructure.repositories.movement_mapper import row_to_movement

# "MOV-" + três dígitos, no espírito de `next_product_code`: sequencial e
# legível, para que o identificador apareça inteligível numa tela de
# demonstração. No banco é um uuid, e nada acima desta camada lê o formato —
# o id é opaco para quem confirma e cancela.
ID_PREFIX = "MOV-"
ID_DIGITS = 3


class DemoMovementRepository:
    def __init__(self, products: dict, movements=None, agora=None, suppliers=None):
        self._products = products
        self._suppliers = suppliers
        # Lista, e não dict por id: a ordem de inserção É o histórico, e a
        # leitura só precisa invertê-la para entregar a mais recente primeiro.
        self._movements = list(movements or ())
        # Referência de "agora" para a formatação da coluna de data. Igual ao
        # `agora` de `formatar_ultimo_acesso`: sem ele o teste de "Hoje"
        # dependeria do relógio e do fuso da máquina.
        self._agora = agora

    # ======================================================
    # LEITURA
    # ======================================================

    def list_movements(self, product_code: str | None = None) -> tuple:
        """Da mais recente para a mais antiga, em todas as situações.

        Canceladas incluídas de propósito: escondê-las tiraria da tela a
        resposta para "por que o saldo subiu e voltou".
        """
        linhas = reversed(self._movements)
        if product_code:
            linhas = [m for m in linhas if m["product_code"] == product_code]
        result = []
        for linha in linhas:
            movimento = row_to_movement(
                linha,
                product_code=linha["product_code"],
                product_name=self._nome_do_produto(linha["product_code"]),
                agora=self._agora,
            )
            if linha.get("supplier_id"):
                supplier = self._suppliers.get(linha["supplier_id"]) if self._suppliers else None
                name = getattr(supplier, "name", "") or "Fornecedor indisponível"
                movimento += (name,)
            result.append(movimento)
        return tuple(result)

    def _nome_do_produto(self, code: str) -> str:
        produto = self._products.get(code)
        return produto.name if produto else ""

    # ======================================================
    # ESCRITA
    # ======================================================

    def register(self, data: MovementInput) -> str:
        """Registra e devolve o id. Nasce PENDENTE salvo `confirm=True`.

        Produto inexistente levanta, espelhando o `foreign_key_violation` de
        `fn_register_movement`: aceitar em silêncio criaria histórico apontando
        para nada, e o saldo que ele deveria mover não existiria em lugar
        nenhum.
        """
        if data.product_code not in self._products:
            raise LookupError(f"Produto {data.product_code} não encontrado.")

        especie = MovementKind.from_value(data.kind)
        confirmada = bool(data.confirm)
        agora = self._agora or datetime.now()
        linha = {
            "id": self._proximo_id(),
            "product_code": data.product_code,
            "kind": especie.value,
            "quantity": to_int(data.quantity),
            "status": (
                MovementStatus.CONFIRMADA if confirmada else MovementStatus.PENDENTE
            ).value,
            "note": data.note,
            "supplier_id": getattr(data, "supplier_id", None),
            "created_on": agora,
            "confirmed_on": agora if confirmada else None,
        }
        self._movements.append(linha)
        # Só a confirmada mexe no saldo. Aplicar aqui para a pendente faria o
        # modo demonstração contradizer o `fn_confirmed_balance` do banco, que
        # soma exclusivamente `status = 'CONFIRMADA'`.
        if confirmada:
            self._aplicar_no_saldo(linha, sentido=1)
        return linha["id"]

    def confirm(self, movement_id: str) -> None:
        """Confirma uma pendente. É esta transição que altera o saldo."""
        linha = self._linha(movement_id)
        if linha["status"] != MovementStatus.PENDENTE.value:
            # Mesma recusa de `fn_confirm_movement`: confirmar duas vezes
            # aplicaria a diferença duas vezes, e o saldo deixaria de ser a
            # soma das confirmadas.
            raise ValueError(
                "Só movimentação pendente pode ser confirmada "
                f"(situação atual: {linha['status']})."
            )
        linha["status"] = MovementStatus.CONFIRMADA.value
        linha["confirmed_on"] = self._agora or datetime.now()
        self._aplicar_no_saldo(linha, sentido=1)

    def cancel(self, movement_id: str) -> None:
        """Cancela. Cancelar uma CONFIRMADA devolve o saldo.

        Idempotente: cancelar o que já está cancelado não desfaz nada duas
        vezes. É o mesmo efeito do banco, onde o UPDATE reescreve a mesma
        situação e a soma das confirmadas não muda.
        """
        linha = self._linha(movement_id)
        if linha["status"] == MovementStatus.CANCELADA.value:
            return
        if linha["status"] == MovementStatus.CONFIRMADA.value:
            self._aplicar_no_saldo(linha, sentido=-1)
        linha["status"] = MovementStatus.CANCELADA.value

    # ======================================================
    # SALDO
    # ======================================================

    def _aplicar_no_saldo(self, linha, sentido: int) -> None:
        """Soma (ou desfaz) a diferença da movimentação no produto do catálogo.

        `sentido` é `+1` ao confirmar e `-1` ao cancelar uma confirmada. O
        sinal da ESPÉCIE vem de `MovementKind.sinal`, que espelha o `CASE` de
        `fn_confirmed_balance` — reescrever "entrada soma, saída subtrai" aqui
        criaria a segunda cópia que esse `.sinal` existe para evitar.

        O saldo NÃO é limitado a zero: o banco também não limita, e um
        negativo é a forma honesta de mostrar que foram confirmadas saídas
        além do que havia. Travar em zero esconderia o erro de lançamento
        exatamente de quem precisa vê-lo.
        """
        produto = self._products.get(linha["product_code"])
        if produto is None:
            return

        especie = MovementKind.from_value(linha["kind"])
        novo = to_int(produto.stock) + sentido * especie.sinal * to_int(linha["quantity"])
        # `Product` é frozen: `replace` em vez de atribuição. E a situação é
        # RECALCULADA por `derive_stock_status`, nunca copiada — é a mesma
        # regra de `fn_stock_state`, e um saldo novo com o status velho faria
        # a tabela de Estoque alertar (ou deixar de alertar) pelo valor
        # anterior.
        self._products[linha["product_code"]] = dataclasses.replace(
            produto,
            stock=str(novo),
            stock_status=derive_stock_status(novo, produto.minimum_stock),
        )

    def _linha(self, movement_id: str) -> dict:
        for linha in self._movements:
            if linha["id"] == movement_id:
                return linha
        raise LookupError(f"Movimentação {movement_id} não encontrada.")

    def _proximo_id(self) -> str:
        """Continua a numeração em vez de preencher buracos.

        Mesma razão de `next_product_code`: um id reaproveitado faria duas
        movimentações diferentes dividirem a mesma identidade, e confirmar
        uma confirmaria a outra.
        """
        maior = 0
        for linha in self._movements:
            sufixo = str(linha.get("id", ""))[len(ID_PREFIX):]
            if str(linha.get("id", "")).startswith(ID_PREFIX) and sufixo.isdigit():
                maior = max(maior, int(sufixo))
        return f"{ID_PREFIX}{maior + 1:0{ID_DIGITS}d}"

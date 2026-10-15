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
from stockflow.domain.enums.adjustment_reason import AdjustmentReason
from stockflow.domain.enums.movement_kind import MovementKind
from stockflow.domain.enums.movement_status import MovementStatus
from stockflow.domain.exceptions.adjustment_errors import SaldoDesatualizadoError
from stockflow.domain.stock_adjustment import calcular_ajuste, saldo_contado
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
            supplier_name = ""
            if linha.get("supplier_id"):
                supplier = (
                    self._suppliers.get(linha["supplier_id"])
                    if self._suppliers else None
                )
                supplier_name = getattr(supplier, "name", "") or "Fornecedor indisponível"
            result.append(row_to_movement(
                linha,
                product_code=linha["product_code"],
                product_name=self._nome_do_produto(linha["product_code"]),
                agora=self._agora,
                supplier_name=supplier_name,
            ))
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

        if not self._products[data.product_code].active:
            raise ValueError("Selecione um produto ativo.")
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
        # Só a confirmada mexe no saldo. Aplicar aqui para a pendente faria o
        # modo demonstração contradizer o `fn_confirmed_balance` do banco, que
        # soma exclusivamente `status = 'CONFIRMADA'`.
        if confirmada:
            self._aplicar_no_saldo(linha, sentido=1)
        self._movements.append(linha)
        return linha["id"]

    def confirm(self, movement_id: str) -> None:
        """Confirma uma pendente. É esta transição que altera o saldo."""
        linha = self._linha(movement_id)
        if not self._products[linha["product_code"]].active:
            raise ValueError("Produto inativo não pode ser movimentado.")
        if linha["status"] != MovementStatus.PENDENTE.value:
            # Mesma recusa de `fn_confirm_movement`: confirmar duas vezes
            # aplicaria a diferença duas vezes, e o saldo deixaria de ser a
            # soma das confirmadas.
            raise ValueError(
                "Só movimentação pendente pode ser confirmada "
                f"(situação atual: {linha['status']})."
            )
        self._aplicar_no_saldo(linha, sentido=1)
        linha["status"] = MovementStatus.CONFIRMADA.value
        linha["confirmed_on"] = self._agora or datetime.now()

    def cancel(self, movement_id: str) -> None:
        """Cancela. Cancelar uma CONFIRMADA devolve o saldo.

        Idempotente: cancelar o que já está cancelado não desfaz nada duas
        vezes. É o mesmo efeito do banco, onde o UPDATE reescreve a mesma
        situação e a soma das confirmadas não muda.
        """
        linha = self._linha(movement_id)
        if linha.get("sale_id"):
            raise ValueError("A saída pertence a uma venda e não pode ser cancelada isoladamente.")
        if linha["status"] == MovementStatus.CANCELADA.value:
            return
        if linha["status"] == MovementStatus.CONFIRMADA.value:
            self._aplicar_no_saldo(linha, sentido=-1)
        linha["status"] = MovementStatus.CANCELADA.value

    def adjust(self, data) -> str:
        """Ajuste manual de inventário, imitando `fn_register_adjustment`.

        A ordem das recusas é a MESMA da função SQL
        (`database/code/procedures/04a_movements.sql`), e isso não é
        capricho: o modo demonstração que aceitasse o que o Postgres recusa
        esconderia o bug de quem não roda com banco até a primeira gravação
        real — e, pior, a MESMA entrada errada produziria uma mensagem
        diferente aqui e lá, o que já custou caro neste projeto (ver a nota
        do README sobre a regra de `stock_status` que divergia de
        `fn_stock_state` em 5 de 11 casos antes de alguém notar).

        O saldo resultante é conferido ANTES de mexer no catálogo. Lá a
        garantia vem da transação; aqui não há transação, então a única
        forma de não deixar estado pela metade é calcular, conferir e só
        então aplicar.
        """
        # `saldo_contado`, e não `to_int`: o padrão zero de `to_int` existe
        # para não derrubar uma listagem por causa de uma célula ilegível, e
        # aqui zero não é um valor neutro — é a contagem que ESVAZIA o
        # produto. Um contado ausente ou ilegível tem que recusar, como o
        # `p_counted_balance IS NULL` do banco recusa.
        contado = saldo_contado(data.counted_balance)
        if contado < 0:
            # Espelha o guard `p_counted_balance IS NULL OR
            # p_counted_balance < 0` da função SQL, que roda ANTES até de
            # travar a linha do produto: um contado negativo é erro de
            # entrada, e não depende de qual produto foi escolhido.
            # `calcular_ajuste` faz a MESMA checagem mais abaixo, mas só
            # depois de resolver produto e saldo esperado — tarde demais
            # para honrar esta ordem, por isso o guard se repete aqui em vez
            # de mover a chamada de `calcular_ajuste` para cima (o que
            # obrigaria a resolver `atual` antes da hora).
            raise ValueError(f"O saldo contado não pode ser negativo (recebido: {contado}).")

        motivo = AdjustmentReason.from_value(data.reason)
        detalhe = str(data.detail or "").strip()
        if motivo.exige_detalhe and not detalhe:
            raise ValueError('O motivo "Outro" exige uma justificativa escrita.')

        produto = self._products.get(data.product_code)
        if produto is None:
            raise LookupError(f"Produto {data.product_code} não encontrado.")
        if not produto.active:
            raise ValueError("Selecione um produto ativo.")

        atual = to_int(produto.stock)
        esperado = data.expected_balance
        if esperado is not None and to_int(esperado) != atual:
            raise SaldoDesatualizadoError.de_saldos(to_int(esperado), atual)

        especie, quantidade = calcular_ajuste(atual, contado)

        # A conferência do saldo resultante, antes de qualquer escrita. Se
        # `calcular_ajuste` e `_aplicar_no_saldo` algum dia discordarem, é
        # aqui que aparece — e nada foi alterado ainda.
        if atual + especie.sinal * quantidade != contado:
            raise AssertionError(
                f"Ajuste calculado levaria o saldo a "
                f"{atual + especie.sinal * quantidade}, não ao contado {contado}."
            )

        agora = self._agora or datetime.now()
        linha = {
            "id": self._proximo_id(),
            "product_code": data.product_code,
            "kind": especie.value,
            "quantity": quantidade,
            "status": MovementStatus.CONFIRMADA.value,
            "note": detalhe,
            "supplier_id": None,
            "adjustment_reason": motivo.value,
            "counted_balance": contado,
            "created_on": agora,
            "confirmed_on": agora,
        }
        self._aplicar_no_saldo(linha, sentido=1)
        self._movements.append(linha)
        return linha["id"]

    def register_sale(self, sale_id, itens):
        """Valida o carrinho inteiro antes de registrar qualquer saída."""
        quantidades = {}
        for item in itens:
            code = item["product"].code
            quantidades[code] = quantidades.get(code, 0) + item["quantity"]
        for code, quantity in quantidades.items():
            produto = self._products.get(code)
            if produto is None or not produto.active:
                raise ValueError("Selecione um produto ativo válido.")
            if to_int(produto.stock) < quantity:
                raise ValueError(
                    f"Estoque insuficiente para {produto.name} "
                    f"(disponível: {produto.stock}, vendido: {quantity})."
                )
        for code, quantity in quantidades.items():
            movement_id = self.register(MovementInput(
                code, MovementKind.SAIDA, quantity,
                note=f"Venda {sale_id}", confirm=True,
            ))
            self._linha(movement_id)["sale_id"] = str(sale_id)

    # ======================================================
    # SALDO
    # ======================================================

    def _aplicar_no_saldo(self, linha, sentido: int) -> None:
        """Soma (ou desfaz) a diferença da movimentação no produto do catálogo.

        `sentido` é `+1` ao confirmar e `-1` ao cancelar uma confirmada. O
        sinal da ESPÉCIE vem de `MovementKind.sinal`, que espelha o `CASE` de
        `fn_confirmed_balance` — reescrever "entrada soma, saída subtrai" aqui
        criaria a segunda cópia que esse `.sinal` existe para evitar.

        Saldo negativo é recusado antes de modificar catálogo ou histórico,
        espelhando a constraint products.stock >= 0 do PostgreSQL.
        """
        produto = self._products.get(linha["product_code"])
        if produto is None:
            return

        especie = MovementKind.from_value(linha["kind"])
        novo = to_int(produto.stock) + sentido * especie.sinal * to_int(linha["quantity"])
        if novo < 0:
            raise ValueError("Saldo insuficiente para esta movimentação.")
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

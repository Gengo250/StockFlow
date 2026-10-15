"""Casos de uso de movimentação de estoque (US03/US04).

Mesmo desenho do `ProductService`: a permissão é verificada ANTES de qualquer
chamada ao repositório, inclusive antes de leitura. Um papel sem alçada não
pode nem sondar o histórico para descobrir o que a empresa movimentou.

A checagem aqui não substitui a do banco — `fn_register_movement` e as irmãs
checam `fn_has_role` por conta própria. São camadas: esta dá a mensagem certa
na tela sem gastar requisição, aquela é a que de fato impede a gravação.
"""

from stockflow.application.dto.adjustment_input import AdjustmentInput
from stockflow.application.dto.movement_input import MovementInput
from stockflow.application.ports.movement_repository import MovementRepository
from stockflow.domain.enums.adjustment_reason import AdjustmentReason
from stockflow.domain.enums.movement_kind import MovementKind
from stockflow.domain.permissions import ensure_can_move_stock
from stockflow.domain.stock_adjustment import calcular_ajuste, saldo_contado


class MovementService:
    def __init__(self, repository: MovementRepository, supplier_repository=None, product_repository=None):
        self._repository = repository
        self._supplier_repository = supplier_repository
        self._product_repository = product_repository

    def list_movements(self, session, product_code: str | None = None) -> tuple:
        ensure_can_move_stock(session, action="consultar movimentações")
        return self._repository.list_movements(product_code)

    def register(self, session, data: MovementInput) -> str:
        """Registra uma movimentação. Levanta `ValueError` em dado inválido."""
        ensure_can_move_stock(session, action="registrar movimentações")

        if not (data.product_code or "").strip():
            raise ValueError("Selecione o produto da movimentação.")

        if self._product_repository is not None:
            product = self._product_repository.get(data.product_code)
            if product is None or not product.active:
                raise ValueError("Selecione um produto ativo.")

        # Quantidade positiva é regra de domínio, não só CHECK do banco: sem
        # ela, a tela mandaria zero e receberia de volta uma mensagem do
        # Postgres, em inglês e fora de contexto.
        quantidade = _para_inteiro(data.quantity)
        if quantidade <= 0:
            raise ValueError("A quantidade deve ser maior que zero.")

        # Normaliza a espécie aqui para que um valor desconhecido estoure
        # antes da ida à rede, com o nome do campo na mensagem.
        MovementKind.from_value(data.kind)
        if data.supplier_id:
            if self._supplier_repository is None:
                raise ValueError("Não foi possível validar o fornecedor da entrada.")
            supplier = self._supplier_repository.get(data.supplier_id)
            if supplier is None or not supplier.active:
                raise ValueError("Selecione um fornecedor ativo.")

        return self._repository.register(data)

    def confirm(self, session, movement_id: str) -> None:
        """Confirma uma pendente. É esta transição que altera o saldo."""
        ensure_can_move_stock(session, action="confirmar movimentações")
        self._repository.confirm(movement_id)

    def cancel(self, session, movement_id: str) -> None:
        ensure_can_move_stock(session, action="cancelar movimentações")
        self._repository.cancel(movement_id)
    def adjust(self, session, data: MovementInput) -> str:
        data = replace(data, origin="MANUAL")
        self._ensure_can_move_stock(session, "realizar ajustes manuais de estoque")
        if not (data.note or "").strip():
            raise ValueError("A justificativa é obrigatória para ajustes manuais de estoque.")
        if data.quantity <= 0:
            raise ValueError("A quantidade do ajuste deve ser um valor positivo. Use o campo 'kind' para definir Entrada ou Saída.")
        return self._repository.adjust(data)

    def adjust(self, session, data: AdjustmentInput) -> str:
        """Ajusta o saldo para o valor contado. Levanta `ValueError` em dado inválido.

        Permissão primeiro, como em `register`: a mesma alçada ADMIN/STOCK,
        porque `fn_register_adjustment` checa o mesmo `fn_has_role`. As
        validações abaixo não substituem as do banco — elas dão a mensagem
        certa em português sem gastar requisição, e o banco segue sendo quem
        de fato impede a gravação.
        """
        ensure_can_move_stock(session, action="ajustar o estoque")

        # A ORDEM daqui para baixo é a de `fn_register_adjustment`: contado,
        # motivo, produto. Não é estética. O adaptador de demonstração já
        # espelha essa ordem (e tem teste que a prende), mas este serviço é
        # o caminho por onde TODA chamada real passa — com a checagem de
        # produto antes da de motivo, uma entrada com produto inativo E
        # `OUTRO` sem detalhe recebia "Selecione um produto ativo." onde o
        # banco e a demonstração dizem a mensagem da justificativa. A mesma
        # entrada errada tem que produzir a mesma recusa nas três camadas.
        contado = saldo_contado(data.counted_balance)
        if contado < 0:
            # Espelha o guard `p_counted_balance IS NULL OR
            # p_counted_balance < 0`, que no SQL vem antes de tudo. Aqui ele
            # é explícito porque `calcular_ajuste` — que faz a mesma
            # checagem — pode nem ser chamada: sem saldo esperado, não há o
            # que comparar.
            raise ValueError(f"O saldo contado não pode ser negativo (recebido: {contado}).")

        motivo = AdjustmentReason.from_value(data.reason)
        if motivo.exige_detalhe and not str(data.detail or "").strip():
            raise ValueError('O motivo "Outro" exige uma justificativa escrita.')

        if not (data.product_code or "").strip():
            raise ValueError("Selecione o produto do ajuste.")

        if self._product_repository is not None:
            product = self._product_repository.get(data.product_code)
            if product is None or not product.active:
                raise ValueError("Selecione um produto ativo.")

        # `expected_balance is None` é o opt-out documentado da checagem de
        # concorrência, e os dois adaptadores e a função SQL o respeitam. O
        # serviço precisa respeitá-lo também: convertendo `None` para zero,
        # uma contagem legítima de zero virava "contado igual ao exibido" e
        # era recusada aqui — na única camada por onde toda chamada passa.
        #
        # Quando o saldo exibido EXISTE, `calcular_ajuste` é o que faz a
        # tela receber a recusa nomeada (`AjusteSemEfeitoError`) em vez de
        # uma mensagem do Postgres traduzida pela metade.
        if data.expected_balance is not None:
            calcular_ajuste(_para_inteiro(data.expected_balance), contado)

        return self._repository.adjust(data)


def _para_inteiro(valor) -> int:
    try:
        return int(str(valor).strip() or 0)
    except (ValueError, TypeError):
        return 0

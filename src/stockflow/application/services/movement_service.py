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
from stockflow.domain.stock_adjustment import calcular_ajuste


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

    def adjust(self, session, data: AdjustmentInput) -> str:
        """Ajusta o saldo para o valor contado. Levanta `ValueError` em dado inválido.

        Permissão primeiro, como em `register`: a mesma alçada ADMIN/STOCK,
        porque `fn_register_adjustment` checa o mesmo `fn_has_role`. As
        validações abaixo não substituem as do banco — elas dão a mensagem
        certa em português sem gastar requisição, e o banco segue sendo quem
        de fato impede a gravação.
        """
        ensure_can_move_stock(session, action="ajustar o estoque")

        if not (data.product_code or "").strip():
            raise ValueError("Selecione o produto do ajuste.")

        if self._product_repository is not None:
            product = self._product_repository.get(data.product_code)
            if product is None or not product.active:
                raise ValueError("Selecione um produto ativo.")

        motivo = AdjustmentReason.from_value(data.reason)
        if motivo.exige_detalhe and not str(data.detail or "").strip():
            raise ValueError('O motivo "Outro" exige uma justificativa escrita.')

        # `calcular_ajuste` levanta em contado negativo e em diferença zero.
        # Chamá-la aqui é o que faz a tela receber a recusa nomeada em vez de
        # uma mensagem do Postgres traduzida pela metade.
        calcular_ajuste(_para_inteiro(data.expected_balance),
                        _para_inteiro(data.counted_balance))

        return self._repository.adjust(data)


def _para_inteiro(valor) -> int:
    try:
        return int(str(valor).strip() or 0)
    except (ValueError, TypeError):
        return 0

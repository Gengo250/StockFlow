"""Erro de produto inativo escolhido para uma operação nova."""


class InactiveProductError(ValueError):
    """Produto existe no catálogo, mas está desativado para novas operações.

    Carrega `product_code` e `operation` porque quem trata o erro precisa
    reabrir a seleção no item certo — a mensagem formatada serve ao usuário,
    não ao chamador.
    """

    def __init__(self, code: str, name: str | None, operation):
        self.product_code = code
        self.product_name = name
        self.operation = operation

        operacao = getattr(operation, "label", operation)
        identificacao = f"{code} ({name})" if name else str(code)
        super().__init__(
            f"O produto {identificacao} está inativo e não pode ser usado "
            f"em uma nova {operacao}."
        )

"""Erro de permissão do domínio."""


class PermissionDeniedError(PermissionError):
    """Operação negada por falta de permissão do usuário autenticado."""

    def __init__(self, action: str, role):
        self.action = action
        self.role = role
        papel = getattr(role, "value", role) or "sem sessão"
        super().__init__(
            f"Você não tem permissão para {action}. Papel atual: {papel}."
        )

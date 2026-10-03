"""Rótulos em português dos papéis de usuário.

Ficam fora de `UserRole` de propósito: o enum espelha o tipo `user_role` do
banco e precisa continuar valendo em caixa alta e em inglês. Traduzir lá
tornaria o valor exibido indistinguível do valor gravado.
"""

from stockflow.domain.enums.user_role import UserRole

ROLE_LABELS = {
    UserRole.ADMIN: "Administrador",
    UserRole.STOCK: "Estoque",
    UserRole.SELLER: "Vendedor",
}


def rotulo_de_papel(role) -> str:
    try:
        return ROLE_LABELS[UserRole.from_value(role)]
    except (ValueError, KeyError):
        # Papel desconhecido não pode derrubar o cabeçalho: a tela mostra o
        # valor cru e a permissão continua sendo negada pela política.
        return str(getattr(role, "value", role) or "Sem papel")


def iniciais(nome) -> str:
    """Duas letras para o avatar, como "AF" para Ana Ferreira."""
    partes = [parte for parte in (nome or "").split() if parte]
    if not partes:
        return "US"
    if len(partes) == 1:
        return partes[0][:2].upper()
    return (partes[0][0] + partes[-1][0]).upper()

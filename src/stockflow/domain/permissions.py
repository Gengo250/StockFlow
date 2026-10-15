"""Matriz de perfis e permissões da aplicação (H14).

`PERMISSION_MATRIX` é a fonte única: cada área declara quem a VÊ e quem GRAVA
nela, e nomeia a função ou policy SQL que decide a mesma coisa no banco. Antes
dela, a verdade de permissão vivia em seis lugares — os `frozenset` deste
módulo, o `RESTRICTED_PAGES` da `MainWindow`, os toggles manuais de
`apply_session`, as chamadas `sidebar.set_item_visible`, cada função SQL e cada
policy — e nada forçava os seis a concordar.

Os dois níveis existem porque o banco já os distingue: `suppliers_select` exige
ADMIN/STOCK para LER fornecedores, enquanto `clients_select` usa `fn_is_member`
e deixa os três papéis lerem clientes. Uma matriz de um nível só teria que
escolher entre mentir sobre a leitura ou mentir sobre a escrita.

As chaves são as mesmas de `MENU_ITEMS`/`SYSTEM_ITEMS` em
`presentation/widgets/sidebar.py`, para que navegação e menu consultem a matriz
sem tabela de tradução no meio — tradução é onde as duas voltariam a divergir.

`tests/unit/test_permission_matrix.py` compara esta matriz com o SQL de
`database/code/` e falha quando os dois discordam.
"""

from dataclasses import dataclass

from stockflow.domain.enums.user_role import UserRole
from stockflow.domain.exceptions.permission_denied import PermissionDeniedError

#: Os três papéis. Leitura liberada para todos continua sendo uma decisão
#: explícita — por isso o nome, e não um `None` que significasse "sem regra".
TODOS_OS_PAPEIS: frozenset[UserRole] = frozenset(
    {UserRole.ADMIN, UserRole.STOCK, UserRole.SELLER}
)


@dataclass(frozen=True)
class Area:
    """Uma área do sistema e os papéis que a veem e que gravam nela.

    `fonte_ver` e `fonte_gravar` não são comentário: o teste de espelhamento
    usa esses nomes para achar a regra correspondente em `database/code/` e
    comparar os papéis. Fonte errada aqui é teste verde sobre regra errada.
    """

    ver: frozenset[UserRole]
    gravar: frozenset[UserRole]
    fonte_ver: str
    fonte_gravar: str


_ADMIN = frozenset({UserRole.ADMIN})
_ADMIN_STOCK = frozenset({UserRole.ADMIN, UserRole.STOCK})
_ADMIN_SELLER = frozenset({UserRole.ADMIN, UserRole.SELLER})
_NINGUEM: frozenset[UserRole] = frozenset()


PERMISSION_MATRIX: dict[str, Area] = {
    # Catálogo: o estoquista escreve, o vendedor só olha.
    "estoque": Area(
        ver=TODOS_OS_PAPEIS,
        gravar=_ADMIN_STOCK,
        fonte_ver="products_select",
        fonte_gravar="fn_update_products",
    ),
    "produtos": Area(
        ver=TODOS_OS_PAPEIS,
        gravar=_ADMIN_STOCK,
        fonte_ver="products_select",
        fonte_gravar="fn_create_products",
    ),
    # Movimentação altera saldo, e saldo decide reposição e venda. A policy
    # `stock_movements_select` usa `fn_is_member` e deixaria o vendedor LER o
    # histórico; a aplicação é deliberadamente mais estrita, porque
    # `fn_register_movement` recusa esse papel e uma tela que só lê um
    # histórico que o usuário não pode movimentar não tem uso. A divergência é
    # declarada como exceção nomeada no teste de espelhamento.
    "movimentacoes": Area(
        ver=_ADMIN_STOCK,
        gravar=_ADMIN_STOCK,
        fonte_ver="fn_register_movement",
        fonte_gravar="fn_register_movement",
    ),
    # Fornecedor é o único caso em que o banco já restringe a LEITURA:
    # `suppliers_select` e `fn_list_company_suppliers` exigem ADMIN/STOCK.
    "fornecedores": Area(
        ver=_ADMIN_STOCK,
        gravar=_ADMIN_STOCK,
        fonte_ver="suppliers_select",
        fonte_gravar="fn_create_supplier",
    ),
    # Clientes e vendas invertem o par: quem vende escreve, quem cuida do
    # estoque continua lendo — `clients_select` e `sales_select` usam
    # `fn_is_member`.
    "clientes": Area(
        ver=TODOS_OS_PAPEIS,
        gravar=_ADMIN_SELLER,
        fonte_ver="clients_select",
        fonte_gravar="fn_create_client",
    ),
    "vendas": Area(
        ver=TODOS_OS_PAPEIS,
        gravar=_ADMIN_SELLER,
        fonte_ver="sales_select",
        fonte_gravar="fn_register_sale",
    ),
    # A tela inteira é do ADMIN, não só os seus botões: `fn_list_company_users`
    # recusa o não-admin, então nem a listagem existe para os outros papéis.
    "usuarios": Area(
        ver=_ADMIN,
        gravar=_ADMIN,
        fonte_ver="fn_list_company_users",
        fonte_gravar="fn_save_company_member",
    ),
    # O histórico de preço e custo é a auditoria do catálogo, e a tabela já
    # está restrita ao ADMIN por `price_edit_log_select`. A tela não pode ser
    # mais permissiva que a policy: para STOCK e SELLER ela abriria vazia e
    # pareceria um defeito. `gravar` vazio é literal — a auditoria é escrita
    # pelo trigger, nunca pela tela.
    "historico_precos": Area(
        ver=_ADMIN,
        gravar=_NINGUEM,
        fonte_ver="fn_list_price_edits",
        fonte_gravar="",
    ),
    # Áreas sem gate. `gravar` vazio significa que nada ali grava pela tela —
    # não que a gravação seja livre.
    "dashboard": Area(
        ver=TODOS_OS_PAPEIS,
        gravar=_NINGUEM,
        fonte_ver="fn_stock_panel",
        fonte_gravar="",
    ),
    "relatorios": Area(
        ver=TODOS_OS_PAPEIS,
        gravar=_NINGUEM,
        fonte_ver="fn_company_stock_state",
        fonte_gravar="",
    ),
    "configuracoes": Area(
        ver=TODOS_OS_PAPEIS,
        gravar=_NINGUEM,
        fonte_ver="",
        fonte_gravar="",
    ),
}


def _papel_de(role_or_session) -> UserRole | None:
    """Normaliza a entrada das políticas em um `UserRole` ou `None`.

    Aceita `UserRole`, string de papel ou qualquer objeto com `.role`. Não
    importa `Session` de propósito: a entidade é que depende da política, e
    não o contrário.

    Devolve `None` para sessão ausente e para papel desconhecido — os dois
    casos em que a resposta precisa ser negar.
    """
    if role_or_session is None:
        return None
    role = getattr(role_or_session, "role", role_or_session)
    try:
        return UserRole.from_value(role)
    except ValueError:
        # Papel desconhecido nunca vira permissão: na dúvida, nega.
        return None


def _area(nome: str) -> Area:
    """Área desconhecida nega tudo, em vez de liberar por omissão.

    Chave errada é erro de programação, mas o custo dos dois modos de falhar
    não é o mesmo: liberar por omissão entrega uma tela; negar por omissão
    mostra uma recusa que aparece no primeiro teste manual.
    """
    return PERMISSION_MATRIX.get(nome, Area(_NINGUEM, _NINGUEM, "", ""))


def pode_ver(role_or_session, area: str) -> bool:
    """Quem pode ABRIR a área."""
    return _papel_de(role_or_session) in _area(area).ver


def pode_gravar(role_or_session, area: str) -> bool:
    """Quem pode GRAVAR na área."""
    return _papel_de(role_or_session) in _area(area).gravar


def exigir_ver(session, area: str, action: str) -> None:
    """Levanta `PermissionDeniedError` se a sessão não puder abrir a área."""
    if not pode_ver(session, area):
        raise PermissionDeniedError(action, getattr(session, "role", None))


def exigir_gravar(session, area: str, action: str) -> None:
    """Levanta `PermissionDeniedError` se a sessão não puder gravar na área."""
    if not pode_gravar(session, area):
        raise PermissionDeniedError(action, getattr(session, "role", None))


# --------------------------------------------------------------------------
# API por área, derivada da matriz.
#
# Continua existindo porque é o que os serviços e as telas já chamam, e porque
# `ensure_can_manage_products(session)` lê melhor no meio de um serviço do que
# `exigir_gravar(session, "produtos", "...")`. O que mudou é que estas funções
# deixaram de ser a fonte: hoje todas perguntam à matriz.
# --------------------------------------------------------------------------

PRODUCT_WRITE_ROLES: frozenset[UserRole] = PERMISSION_MATRIX["produtos"].gravar

# `fn_is_admin` não tem lista: ou o papel na empresa é ADMIN, ou a função
# levanta `insufficient_privilege`. Esta é a tradução literal disso.
USER_MANAGEMENT_ROLES: frozenset[UserRole] = PERMISSION_MATRIX["usuarios"].gravar

# Mesma lista de produto, e intencionalmente uma ENTRADA SEPARADA na matriz.
# As duas coincidem hoje porque movimentar estoque e editar catálogo são a
# mesma alçada; se um dia o vendedor puder lançar saída de venda, só a entrada
# de `movimentacoes` muda. Apontar as duas para a mesma área faria essa
# mudança vazar para o catálogo.
MOVEMENT_ROLES: frozenset[UserRole] = PERMISSION_MATRIX["movimentacoes"].gravar

SUPPLIER_MANAGEMENT_ROLES: frozenset[UserRole] = PERMISSION_MATRIX["fornecedores"].gravar

CLIENT_WRITE_ROLES: frozenset[UserRole] = PERMISSION_MATRIX["clientes"].gravar


def can_manage_products(role_or_session) -> bool:
    """Quem pode cadastrar/editar produto: espelha `fn_has_role`."""
    return pode_gravar(role_or_session, "produtos")


def ensure_can_manage_products(session, action: str = "gerenciar produtos") -> None:
    """Levanta `PermissionDeniedError` se a sessão não puder escrever produtos.

    `session is None` também é negado: sessão ausente é usuário não
    autenticado, e falhar aberto aqui deixaria a tela de estoque gravável
    para qualquer um.
    """
    exigir_gravar(session, "produtos", action)


def can_manage_users(role_or_session) -> bool:
    """Quem pode administrar usuários: espelha `fn_is_admin`.

    Inclui LISTAR. `fn_list_company_users` recusa o não-admin, então a tela
    inteira de usuários é privilégio de ADMIN — e não só os seus botões.
    """
    return pode_gravar(role_or_session, "usuarios")


def ensure_can_manage_users(session, action: str = "gerenciar usuários") -> None:
    """Levanta `PermissionDeniedError` se a sessão não for de um ADMIN.

    Mesma regra de falha fechada do caminho de produto: sem sessão, nega.
    """
    exigir_gravar(session, "usuarios", action)


def can_move_stock(role_or_session) -> bool:
    """Quem pode registrar, confirmar ou cancelar movimentação.

    Espelha o `fn_has_role(p_company_id, ARRAY['ADMIN','STOCK'])` que as três
    funções de movimentação checam antes de qualquer gravação.
    """
    return pode_gravar(role_or_session, "movimentacoes")


def ensure_can_move_stock(session, action: str = "movimentar o estoque") -> None:
    """Levanta `PermissionDeniedError` se a sessão não puder movimentar.

    Mesma falha fechada dos demais caminhos: sem sessão, nega. Movimentação
    altera saldo, e saldo é o número que decide reposição e venda.
    """
    exigir_gravar(session, "movimentacoes", action)


def can_view_price_history(role_or_session) -> bool:
    """Quem pode consultar o histórico de preço e custo: só o ADMIN.

    Espelha `fn_is_admin(...)` dentro de `fn_list_price_edits`, que por sua
    vez repete a policy `price_edit_log_select`. É a única área cujo gate é
    de LEITURA e não de escrita — por isso pergunta a `pode_ver`.
    """
    return pode_ver(role_or_session, "historico_precos")


def ensure_can_view_price_history(
    session, action: str = "consultar o histórico de preços"
) -> None:
    """Levanta `PermissionDeniedError` se a sessão não puder abrir o histórico."""
    exigir_ver(session, "historico_precos", action)


def can_manage_suppliers(role_or_session) -> bool:
    """Quem pode consultar e manter fornecedores: ADMIN e STOCK."""
    return pode_gravar(role_or_session, "fornecedores")


def ensure_can_manage_suppliers(
    session, action: str = "gerenciar fornecedores"
) -> None:
    """Negação fechada para sessão ausente e papéis sem alçada."""
    exigir_gravar(session, "fornecedores", action)


def can_manage_clients(role_or_session) -> bool:
    return pode_gravar(role_or_session, "clientes")


def ensure_can_manage_clients(session, action="gerenciar clientes") -> None:
    exigir_gravar(session, "clientes", action)


def ensure_can_register_sales(session) -> None:
    ensure_can_manage_clients(session, action="registrar vendas")

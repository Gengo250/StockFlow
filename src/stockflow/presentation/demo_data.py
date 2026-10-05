"""Base única de pessoas usada pelas telas de Usuários e Vendas.

As duas telas mantinham listas próprias e divergentes: a de Usuários exibia
oito pessoas, a de Vendas conhecia quatro. Quem estava ativo só na primeira
ganhava o botão de carrinho habilitado sem cliente correspondente para
associar, e a associação falhava em silêncio.

Enquanto a integração com o banco não existe, este módulo é a única fonte
desses dados — as duas telas derivam daqui.
"""

from collections import namedtuple

from stockflow.presentation.demo_status import is_demo_user_active
from stockflow.presentation.user_directory_row import UserDirectoryRow

_CLIENT_ACTIVE_BY_ID = {}


def is_demo_client_active(client_id, default=True):
    return _CLIENT_ACTIVE_BY_ID.get(str(client_id), default)


def set_demo_client_active(client_id, active):
    if not client_id:
        raise ValueError("O cliente demonstrativo precisa de um identificador.")
    _CLIENT_ACTIVE_BY_ID[str(client_id)] = bool(active)


def reset_demo_client_statuses():
    _CLIENT_ACTIVE_BY_ID.clear()

DemoPerson = namedtuple(
    "DemoPerson",
    "cliente_id user_id name login department role status last_access color",
)


# O campo `role` usa os RÓTULOS dos papéis reais do banco
# (`public.user_role`, traduzidos em presentation/roles.py). A demonstração
# tinha perfis próprios — "Gerente", "Operador", "Financeiro" — que nenhum
# cadastro conseguiria gravar: o formulário só oferece os papéis do enum, e
# editar uma dessas pessoas caía num perfil que não era o dela.
DEMO_PEOPLE = (
    DemoPerson("CLI-001", "USR-001", "Ana Ferreira", "ana.ferreira@stockflow.com.br", "TI", "Administrador", "Ativo", "Hoje, 09:14", "#8129FF"),
    DemoPerson("CLI-002", "USR-002", "Carlos Mendes", "c.mendes@stockflow.com.br", "Estoque", "Estoque", "Ativo", "Hoje, 08:47", "#195BFF"),
    DemoPerson("CLI-004", "USR-004", "Juliana Ramos", "j.ramos@stockflow.com.br", "Vendas", "Vendedor", "Ativo", "Ontem, 17:30", "#00A77A"),
    DemoPerson("CLI-005", "USR-005", "Roberto Souza", "r.souza@stockflow.com.br", "Estoque", "Estoque", "Ativo", "Ontem, 16:05", "#E98600"),
    DemoPerson("CLI-003", "USR-003", "Patrícia Lima", "p.lima@stockflow.com.br", "Financeiro", "Administrador", "Inativo", "12/08/2026", "#E21885"),
    DemoPerson("CLI-006", "USR-006", "Diego Alves", "d.alves@stockflow.com.br", "Vendas", "Vendedor", "Ativo", "28/09/2026, 07:52", "#009BB9"),
    DemoPerson("CLI-007", "USR-007", "Mariana Costa", "m.costa@stockflow.com.br", "Compras", "Estoque", "Pendente", "Nunca", "#6045F5"),
    DemoPerson("CLI-008", "USR-008", "Felipe Torres", "f.torres@stockflow.com.br", "Financeiro", "Vendedor", "Ativo", "27/09/2026, 18:11", "#EF6500"),
)


def linhas_de_usuarios():
    """Tuplas na ordem esperada pela tabela da tela de Usuários."""
    linhas = []
    for person in DEMO_PEOPLE:
        active = is_demo_user_active(
            person.user_id, default=person.status != "Inativo"
        )
        status = (
            "Inativo" if not active
            else person.status if person.status == "Pendente"
            else "Ativo"
        )
        linhas.append(UserDirectoryRow(
            (
                person.name, person.login, person.department, person.role,
                status, person.last_access, person.color,
            ),
            user_id=person.user_id,
        ))
    return tuple(linhas)


def _status_do_cliente(person):
    active = is_demo_client_active(
        person.cliente_id,
        default=is_demo_user_active(person.user_id, default=person.status != "Inativo"),
    )
    if person.status == "Pendente":
        return "Pendente"
    return "Ativo" if active else "Inativo"


def base_de_clientes():
    """Clientes da tela de Vendas, um por pessoa cadastrada em Usuários."""
    return [
        {"id": p.cliente_id, "nome": p.name, "status": _status_do_cliente(p)}
        for p in DEMO_PEOPLE
    ]


def linhas_de_clientes():
    """Lista de clientes em formato de linha de manutenção da tela."""
    return [
        {
            "id": p.cliente_id,
            "nome": p.name,
            "email": p.login,
            "telefone": "",
            "documento": "",
            "status": _status_do_cliente(p),
        }
        for p in DEMO_PEOPLE
    ]

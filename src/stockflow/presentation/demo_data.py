"""Base única de pessoas usada pelas telas de Usuários e Vendas.

As duas telas mantinham listas próprias e divergentes: a de Usuários exibia
oito pessoas, a de Vendas conhecia quatro. Quem estava ativo só na primeira
ganhava o botão de carrinho habilitado sem cliente correspondente para
associar, e a associação falhava em silêncio.

Enquanto a integração com o banco não existe, este módulo é a única fonte
desses dados — as duas telas derivam daqui.
"""

from collections import namedtuple

DemoPerson = namedtuple(
    "DemoPerson",
    "cliente_id name login department role status last_access color",
)


DEMO_PEOPLE = (
    DemoPerson("CLI-001", "Ana Ferreira", "ana.ferreira@stockflow.com.br", "TI", "Administrador", "Ativo", "Hoje, 09:14", "#8129FF"),
    DemoPerson("CLI-002", "Carlos Mendes", "c.mendes@stockflow.com.br", "Estoque", "Gerente", "Ativo", "Hoje, 08:47", "#195BFF"),
    DemoPerson("CLI-004", "Juliana Ramos", "j.ramos@stockflow.com.br", "Vendas", "Operador", "Ativo", "Ontem, 17:30", "#00A77A"),
    DemoPerson("CLI-005", "Roberto Souza", "r.souza@stockflow.com.br", "Estoque", "Operador", "Ativo", "Ontem, 16:05", "#E98600"),
    DemoPerson("CLI-003", "Patrícia Lima", "p.lima@stockflow.com.br", "Financeiro", "Financeiro", "Inativo", "12/08/2026", "#E21885"),
    DemoPerson("CLI-006", "Diego Alves", "d.alves@stockflow.com.br", "Vendas", "Gerente", "Ativo", "28/09/2026, 07:52", "#009BB9"),
    DemoPerson("CLI-007", "Mariana Costa", "m.costa@stockflow.com.br", "Compras", "Operador", "Pendente", "Nunca", "#6045F5"),
    DemoPerson("CLI-008", "Felipe Torres", "f.torres@stockflow.com.br", "Financeiro", "Financeiro", "Ativo", "27/09/2026, 18:11", "#EF6500"),
)


def linhas_de_usuarios():
    """Tuplas na ordem esperada pela tabela da tela de Usuários."""
    return tuple(
        (p.name, p.login, p.department, p.role, p.status, p.last_access, p.color)
        for p in DEMO_PEOPLE
    )


def base_de_clientes():
    """Clientes da tela de Vendas, um por pessoa cadastrada em Usuários."""
    return [
        {"id": p.cliente_id, "nome": p.name, "status": p.status}
        for p in DEMO_PEOPLE
    ]

"""Tradução do retorno de `fn_list_company_users` para a linha da tela.

A tabela de Usuários consome tuplas neste contrato, herdado de `demo_data`:

    (nome, login, departamento, perfil, status, último acesso, cor)

Manter o MESMO formato é deliberado: a tela não precisa saber se a linha veio
do banco ou da demonstração, e trocar a fonte não vira refatoração de widget.

Três campos não existem como coluna e são derivados aqui:

- **perfil** — `user_role` traduzido por `presentation/roles.py`. O enum do
  banco é ADMIN/STOCK/SELLER e precisa continuar assim; quem traduz é a tela.
- **status** — combina `is_active` com `last_access`, porque a tela tem três
  estados e o banco tem um booleano. Ver `derivar_status`.
- **cor** — identidade visual do avatar. Não é dado de negócio; é derivada do
  id para ficar estável entre sessões.
"""

from datetime import datetime, timezone

from stockflow.presentation.roles import rotulo_de_papel

ATIVO = "Ativo"
INATIVO = "Inativo"
PENDENTE = "Pendente"

NUNCA = "Nunca"

# Mesma paleta da base de demonstração, para que a tela não mude de aparência
# ao trocar a fonte dos dados.
CORES = (
    "#8129FF", "#195BFF", "#00A77A", "#E98600",
    "#E21885", "#009BB9", "#6045F5", "#EF6500",
)


def cor_do_usuario(user_id) -> str:
    """Cor estável do avatar, derivada do id.

    Determinística de propósito: sortear deixaria o mesmo usuário mudando de
    cor a cada abertura da tela, e a cor é justamente o que o olho usa para
    reencontrar a linha. `hash()` do Python não serve — ele é aleatorizado por
    processo (PYTHONHASHSEED), então variaria entre execuções.
    """
    texto = str(user_id or "")
    return CORES[sum(texto.encode()) % len(CORES)] if texto else CORES[0]


def derivar_status(is_active, last_access) -> str:
    """Os três estados da tela, a partir de `active` + último acesso.

    O banco só tem um booleano, mas a tela distingue quem foi desativado de
    quem nunca entrou — e a diferença importa para o administrador: "Inativo"
    pede reativação, "Pendente" pede que a pessoa aceite o convite. Colapsar
    os dois em "Ativo" esconderia a conta que foi criada e nunca usada.
    """
    if not is_active:
        return INATIVO
    return ATIVO if last_access else PENDENTE


def _para_datetime(valor):
    """ISO do PostgREST para `datetime`, ou `None`.

    Devolve `None` em vez de levantar: um carimbo ilegível vale "nunca
    acessou" na tela, e não vale derrubar a listagem inteira de usuários.
    """
    if valor is None or isinstance(valor, datetime):
        return valor
    texto = str(valor).strip()
    if not texto:
        return None
    try:
        return datetime.fromisoformat(texto)
    except ValueError:
        return None


def formatar_ultimo_acesso(valor, agora=None) -> str:
    """"Hoje, 09:14" / "Ontem, 17:30" / "12/08/2026" / "Nunca".

    `agora` é parâmetro para que o teste possa fixar a referência: com
    `datetime.now()` embutido, o teste de "Hoje" passaria hoje e falharia na
    virada do dia.

    A comparação é feita no fuso LOCAL. O banco guarda `timestamptz` em UTC, e
    comparar datas em UTC faria um acesso das 22h de ontem aparecer como
    "Hoje" para quem está em UTC-3.
    """
    momento = _para_datetime(valor)
    if momento is None:
        return NUNCA

    if momento.tzinfo is not None:
        momento = momento.astimezone()
    referencia = agora or datetime.now(tz=momento.tzinfo)
    if referencia.tzinfo is not None and momento.tzinfo is None:
        momento = momento.replace(tzinfo=referencia.tzinfo)
    if referencia.tzinfo is None and momento.tzinfo is not None:
        momento = momento.replace(tzinfo=None)

    dias = (referencia.date() - momento.date()).days
    if dias == 0:
        return f"Hoje, {momento:%H:%M}"
    if dias == 1:
        return f"Ontem, {momento:%H:%M}"
    return f"{momento:%d/%m/%Y}"


def row_to_user(row, agora=None) -> tuple:
    """Linha de `fn_list_company_users` na tupla que a tabela desenha."""
    last_access = row.get("last_access")
    return (
        row.get("display_name") or row.get("login") or "",
        row.get("login") or "",
        row.get("department") or "—",
        rotulo_de_papel(row.get("user_role")),
        derivar_status(row.get("is_active", False), last_access),
        formatar_ultimo_acesso(last_access, agora),
        cor_do_usuario(row.get("user_id")),
    )


def rows_to_users(rows, agora=None) -> tuple:
    return tuple(row_to_user(row, agora) for row in rows or ())


def utc_agora() -> datetime:
    return datetime.now(timezone.utc)

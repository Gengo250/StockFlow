"""Diretório de usuários vindo do banco: tradução e leitura.

A tela de Usuários mostra três coisas que `company_users` não tem como
coluna — perfil em português, status com três estados e "último acesso"
legível. Elas são derivadas, e é aqui que se prova que a derivação não
inventa: um usuário desativado não pode virar "Pendente", e quem nunca
entrou não pode aparecer como "Ativo".
"""

import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from stockflow.domain.enums.user_role import UserRole
from stockflow.domain.exceptions.permission_denied import PermissionDeniedError
from stockflow.infrastructure.repositories.supabase_user_repository import (
    SupabaseUserRepository,
)
from stockflow.infrastructure.repositories.user_mapper import (
    CORES,
    cor_do_usuario,
    derivar_status,
    formatar_ultimo_acesso,
    row_to_user,
)

COMPANY = "11111111-1111-1111-1111-111111111111"
USER_ID = "44444444-4444-4444-4444-444444444444"

# Referência no fuso LOCAL, não em UTC. O formatador converte `timestamptz`
# para o fuso de quem olha a tela — um acesso das 22h de ontem em UTC é
# "Ontem" para quem está em UTC-3, não "Hoje". Fixar a referência em UTC
# faria estes testes passarem só em máquina configurada em UTC.
AGORA = datetime(2026, 10, 4, 15, 0).astimezone()


def linha(**overrides):
    base = {
        "user_id": USER_ID,
        "login": "teste.stockflow@gmail.com",
        "display_name": "Miguel",
        "department": "TI",
        "user_role": "ADMIN",
        "is_active": True,
        "last_access": AGORA - timedelta(hours=2),
        "created_on": AGORA - timedelta(days=30),
    }
    base.update(overrides)
    return base


# ------------------------------------------------------------------- status


def test_status_separa_desativado_de_nunca_acessou():
    """Três estados a partir de um booleano e um carimbo.

    Colapsar "Pendente" em "Ativo" esconderia a conta criada e nunca usada —
    justamente a que precisa de providência do administrador.
    """
    assert derivar_status(True, AGORA) == "Ativo"
    assert derivar_status(True, None) == "Pendente"
    assert derivar_status(False, AGORA) == "Inativo"
    # Desativado ganha de nunca ter entrado: quem foi desligado não está
    # "pendente de aceitar convite".
    assert derivar_status(False, None) == "Inativo"


# ------------------------------------------------------------ último acesso


@pytest.mark.parametrize("delta,esperado", [
    (timedelta(hours=2), "Hoje, 13:00"),
    (timedelta(days=1), "Ontem, 15:00"),
    (timedelta(days=5), "29/09/2026"),
])
def test_ultimo_acesso_e_relativo_so_nos_dois_dias_recentes(delta, esperado):
    assert formatar_ultimo_acesso(AGORA - delta, agora=AGORA) == esperado


def test_sem_acesso_registrado_mostra_nunca():
    assert formatar_ultimo_acesso(None, agora=AGORA) == "Nunca"


def test_carimbo_chega_como_texto_iso_do_postgrest():
    """O cliente entrega `timestamptz` como string, não como datetime."""
    iso = (AGORA - timedelta(hours=2)).isoformat()
    assert formatar_ultimo_acesso(iso, agora=AGORA) == "Hoje, 13:00"


def test_carimbo_em_utc_e_convertido_para_o_fuso_de_quem_olha():
    """O banco guarda em UTC; a tela precisa mostrar a hora local.

    Sem a conversão, quem está em UTC-3 veria "Hoje, 02:00" para um acesso
    que aconteceu às 23:00 de ontem — hora errada E dia errado.
    """
    momento = AGORA - timedelta(hours=2)
    em_utc = momento.astimezone(timezone.utc)
    assert formatar_ultimo_acesso(em_utc, agora=AGORA) == "Hoje, 13:00"


def test_carimbo_ilegivel_nao_derruba_a_listagem():
    """Uma data podre vale "Nunca", não uma tela de usuários quebrada."""
    assert formatar_ultimo_acesso("ontem de manhã", agora=AGORA) == "Nunca"


# --------------------------------------------------------------------- cor


def test_cor_sai_da_paleta_e_distingue_usuarios():
    assert cor_do_usuario(USER_ID) in CORES
    assert cor_do_usuario("") in CORES
    # Ids diferentes não podem colapsar todos na mesma cor.
    cores = {cor_do_usuario(f"usuario-{i}") for i in range(20)}
    assert len(cores) > 1


def test_cor_e_a_mesma_em_OUTRO_PROCESSO():
    """Prova que a derivação não usa `hash()`, que é aleatorizado por processo.

    Um teste dentro do mesmo processo não distinguiria as duas coisas: com
    `hash()`, as chamadas concordariam aqui e discordariam entre execuções —
    e o usuário veria a cor da linha mudar a cada abertura da aplicação.
    `PYTHONHASHSEED=0` e `=1` dariam respostas diferentes.
    """
    codigo = (
        "import sys; sys.path.insert(0, 'src');"
        "from stockflow.infrastructure.repositories.user_mapper import cor_do_usuario;"
        f"print(cor_do_usuario({USER_ID!r}))"
    )
    saidas = {
        subprocess.run(
            [sys.executable, "-c", codigo],
            cwd=Path(__file__).resolve().parents[2],
            env={**os.environ, "PYTHONHASHSEED": semente},
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        for semente in ("0", "1", "random")
    }
    assert saidas == {cor_do_usuario(USER_ID)}


# ------------------------------------------------------------------- linha


def test_linha_do_banco_vira_a_tupla_que_a_tabela_desenha():
    nome, login, depto, perfil, status, acesso, cor = row_to_user(linha(), agora=AGORA)

    assert nome == "Miguel"
    assert login == "teste.stockflow@gmail.com"
    assert depto == "TI"
    assert perfil == "Administrador"      # ADMIN traduzido por roles.py
    assert status == "Ativo"
    assert acesso == "Hoje, 13:00"
    assert cor.startswith("#")


def test_departamento_vazio_nao_vira_celula_em_branco():
    """Coluna vazia parece bug de carregamento; o travessão diz "não informado"."""
    assert row_to_user(linha(department=None), agora=AGORA)[2] == "—"


def test_conta_sem_vinculo_ainda_aparece_na_lista():
    """Sem `auth_user_id`, a função devolve o login local e nenhum acesso.

    É o usuário sobre o qual o administrador precisa agir; escondê-lo seria
    o pior resultado possível.
    """
    sem_auth = linha(login="miguel", display_name="miguel", last_access=None)
    nome, login, _, _, status, acesso, _ = row_to_user(sem_auth, agora=AGORA)

    assert (nome, login) == ("miguel", "miguel")
    assert status == "Pendente"
    assert acesso == "Nunca"


# -------------------------------------------------------------- repositório


class RespostaFalsa:
    def __init__(self, data):
        self.data = data


class ClienteFalso:
    def __init__(self, resultado=None, erro=None):
        self._resultado = resultado
        self._erro = erro
        self.chamadas = []

    def rpc(self, nome, args):
        self.chamadas.append((nome, args))
        cliente = self

        class _Chamada:
            def execute(self):
                if cliente._erro is not None:
                    raise cliente._erro
                return RespostaFalsa(cliente._resultado)

        return _Chamada()


class ErroDoPostgrest(Exception):
    def __init__(self, message, code=None):
        super().__init__(message)
        self.message = message
        self.code = code


def test_listagem_passa_pela_funcao_e_nao_por_select():
    """`user_accounts` e `company_users` não têm GRANT de SELECT para ninguém.

    O acesso a elas é sempre por função SECURITY DEFINER; um adaptador que
    tentasse `table("company_users")` levaria "permission denied" em runtime.
    """
    cliente = ClienteFalso([linha()])
    usuarios = SupabaseUserRepository(cliente, COMPANY).list_users(agora=AGORA)

    assert cliente.chamadas == [("fn_list_company_users", {"p_company_id": COMPANY})]
    assert usuarios[0][0] == "Miguel"


def test_empresa_sem_usuarios_devolve_lista_vazia_e_nao_erro():
    assert SupabaseUserRepository(ClienteFalso([]), COMPANY).list_users() == ()


def test_recusa_do_banco_vira_erro_de_dominio():
    """A `MainWindow` só captura `PermissionDeniedError`."""
    erro = ErroDoPostgrest("Apenas administradores podem listar usuários", code="42501")
    repo = SupabaseUserRepository(ClienteFalso(erro=erro), COMPANY, role=UserRole.SELLER)

    with pytest.raises(PermissionDeniedError) as capturado:
        repo.list_users()

    assert "administração de usuários" in str(capturado.value)
    assert "SELLER" in str(capturado.value)


def test_departamento_e_gravado_por_funcao_propria():
    """Separada da função de papel: corrigir departamento não é dar ADMIN."""
    cliente = ClienteFalso([])
    SupabaseUserRepository(cliente, COMPANY).set_department(USER_ID, "Compras")

    assert cliente.chamadas == [(
        "fn_set_company_user_department",
        {"p_company_id": COMPANY, "p_user_id": USER_ID, "p_department": "Compras"},
    )]

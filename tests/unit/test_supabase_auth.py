"""Login pelo Supabase Auth e montagem da `Session`.

O que estes testes protegem é a diferença entre "senha errada" e "a conta
existe mas o banco não a reconhece". As duas aparecem para o usuário na mesma
tela, e tratá-las igual é o pior resultado possível numa adoção nova: quem
esqueceu de preencher `user_accounts.auth_user_id` ficaria digitando a senha
certa para sempre, lendo "e-mail ou senha incorretos".
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from stockflow.domain.enums.user_role import UserRole
from stockflow.infrastructure.auth.supabase_auth import (
    CREDENCIAL_INVALIDA,
    SEM_EMPRESA,
    SEM_VINCULO,
    AuthenticationError,
    authenticate,
)

USER_ID = "44444444-4444-4444-4444-444444444444"
COMPANY = "11111111-1111-1111-1111-111111111111"


class RespostaFalsa:
    def __init__(self, data):
        self.data = data


class UsuarioFalso:
    def __init__(self, email, metadata=None):
        self.email = email
        self.user_metadata = metadata or {}


class AuthFalso:
    def __init__(self, user=None, erro=None):
        self._user = user
        self._erro = erro
        self.credenciais = None

    def sign_in_with_password(self, credenciais):
        self.credenciais = credenciais
        if self._erro is not None:
            raise self._erro

        class _Resposta:
            user = self._user

        return _Resposta()


class ClienteFalso:
    def __init__(self, auth, rpc_resultados=None):
        self.auth = auth
        self._rpc = rpc_resultados or {}
        self.chamadas_rpc = []

    def rpc(self, nome, args):
        self.chamadas_rpc.append(nome)
        resultado = self._rpc.get(nome)

        class _Chamada:
            def execute(self_inner):
                return RespostaFalsa(resultado)

        return _Chamada()


def cliente_ok(**overrides):
    rpc = {
        "fn_current_user_id": USER_ID,
        "fn_my_companies": [
            {"company_id": COMPANY, "company_name": "Atlas", "user_role": "ADMIN"}
        ],
    }
    rpc.update(overrides)
    return ClienteFalso(
        AuthFalso(UsuarioFalso("ana.ferreira@example.com", {"name": "Ana Ferreira"})),
        rpc,
    )


# ------------------------------------------------------------------ sucesso


def test_login_monta_a_sessao_com_papel_e_empresa():
    sessao = authenticate(cliente_ok(), "ana.ferreira@example.com", "senha")

    assert sessao.user_id == USER_ID        # id de DOMÍNIO, não o do Auth
    assert sessao.company_id == COMPANY
    assert sessao.role is UserRole.ADMIN
    assert sessao.name == "Ana Ferreira"
    assert sessao.email == "ana.ferreira@example.com"
    assert sessao.can_manage_products is True


def test_papel_do_banco_vale_mesmo_em_caixa_diferente():
    cliente = cliente_ok(fn_my_companies=[{"company_id": COMPANY, "user_role": "seller"}])
    sessao = authenticate(cliente, "juliana@example.com", "senha")

    assert sessao.role is UserRole.SELLER
    assert sessao.can_manage_products is False


def test_email_e_normalizado_antes_de_ir_para_o_auth():
    cliente = cliente_ok()
    authenticate(cliente, "  ana.ferreira@example.com  ", "senha")
    assert cliente.auth.credenciais["email"] == "ana.ferreira@example.com"


def test_nome_cai_no_email_quando_o_auth_nao_tem_metadado():
    """`user_accounts.name` é o login, não serve de nome próprio na tela."""
    cliente = ClienteFalso(
        AuthFalso(UsuarioFalso("carlos.mendes@example.com")),
        {"fn_current_user_id": USER_ID,
         "fn_my_companies": [{"company_id": COMPANY, "user_role": "STOCK"}]},
    )
    assert authenticate(cliente, "carlos.mendes@example.com", "x").name == "carlos.mendes"


# ------------------------------------------------------------------ recusas


def test_credencial_invalida_nao_revela_se_a_conta_existe():
    cliente = ClienteFalso(AuthFalso(erro=Exception("Invalid login credentials")))

    with pytest.raises(AuthenticationError) as erro:
        authenticate(cliente, "quem@example.com", "errada")

    assert str(erro.value) == CREDENCIAL_INVALIDA


def test_auth_sem_usuario_tambem_e_credencial_invalida():
    cliente = ClienteFalso(AuthFalso(user=None))
    with pytest.raises(AuthenticationError, match=CREDENCIAL_INVALIDA):
        authenticate(cliente, "quem@example.com", "x")


def test_conta_sem_vinculo_tem_mensagem_propria():
    """Sem `auth_user_id`, `fn_current_user_id()` devolve NULL.

    Se isto passasse batido, a sessão nasceria sem identidade e a recusa só
    apareceria lá na frente, ao cadastrar produto, como "sem permissão".
    """
    cliente = cliente_ok(fn_current_user_id=None)

    with pytest.raises(AuthenticationError) as erro:
        authenticate(cliente, "nova@example.com", "senha")

    assert str(erro.value) == SEM_VINCULO
    assert "auth_user_id" in str(erro.value)


def test_usuario_sem_empresa_ativa_nao_entra():
    cliente = cliente_ok(fn_my_companies=[])

    with pytest.raises(AuthenticationError, match=SEM_EMPRESA):
        authenticate(cliente, "ana.ferreira@example.com", "senha")


def test_sessao_so_e_montada_depois_das_tres_etapas():
    """A ordem importa: sem JWT, as duas RPCs responderiam como anônimo."""
    cliente = cliente_ok()
    authenticate(cliente, "ana.ferreira@example.com", "senha")

    assert cliente.auth.credenciais is not None
    assert cliente.chamadas_rpc == ["fn_current_user_id", "fn_my_companies"]

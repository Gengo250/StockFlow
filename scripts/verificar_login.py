"""Exercita o caminho AUTENTICADO: login, sessão, catálogo e usuários.

    uv run python scripts/verificar_login.py

A senha é pedida no terminal (sem eco) e não é gravada em lugar nenhum. Dá
para passar o e-mail por argumento ou por `STOCKFLOW_TEST_EMAIL`; a senha
também aceita `STOCKFLOW_TEST_PASSWORD` para uso em script, mas o padrão é
digitar.

POR QUE ESTE SCRIPT EXISTE SEPARADO
-----------------------------------
`test_supabase_connection.py` checa como ANÔNIMO, e o anônimo não tem — nem
deve ter — permissão para nada. Ele consegue provar que as funções EXISTEM,
nunca que elas funcionam. Tudo que depende de identidade (`fn_current_user_id`
resolvendo o JWT, `fn_has_role` concedendo papel, a RLS liberando as linhas da
empresa) só aparece depois de um login de verdade.

SOMENTE LEITURA. Nada é gravado: nenhum produto é criado, nenhum usuário é
alterado. As funções de escrita são verificadas apenas pela EXISTÊNCIA, no
outro script.
"""

import getpass
import os
import sys

from stockflow.infrastructure.auth.supabase_auth import AuthenticationError, authenticate
from stockflow.infrastructure.database.supabase_client import get_client, is_configured
from stockflow.infrastructure.repositories.supabase_product_repository import (
    SupabaseProductRepository,
)
from stockflow.infrastructure.repositories.supabase_user_repository import (
    SupabaseUserRepository,
)

OK = "✓"
FALHA = "✗"
AVISO = "⚠"


def main() -> int:
    if not is_configured():
        print(f"{FALHA} SUPABASE_URL / SUPABASE_PUBLISHABLE_KEY ausentes no .env.")
        return 1

    email = (
        sys.argv[1] if len(sys.argv) > 1
        else os.environ.get("STOCKFLOW_TEST_EMAIL")
        or input("E-mail: ").strip()
    )
    password = os.environ.get("STOCKFLOW_TEST_PASSWORD") or getpass.getpass("Senha: ")

    client = get_client()

    # ---------------------------------------------------------------- login
    print("\n[1] Login")
    try:
        sessao = authenticate(client, email, password)
    except AuthenticationError as erro:
        print(f"  {FALHA} {erro}")
        print("\n  'E-mail ou senha incorretos' = credencial mesmo.")
        print("  'não está vinculada' = falta user_accounts.auth_user_id.")
        print("  'nenhuma empresa'    = falta linha em company_users.")
        print("  Os três casos estão cobertos em scripts/provisionar_usuario.sql.")
        return 1
    except Exception as erro:
        print(f"  {FALHA} {type(erro).__name__}: {erro}")
        return 1

    print(f"  {OK} autenticado como {sessao.name} <{sessao.email}>")
    print(f"  {OK} id de domínio : {sessao.user_id}")
    print(f"  {OK} empresa       : {sessao.company_id}")
    print(f"  {OK} papel         : {sessao.role}")

    falhas = []

    # -------------------------------------------------------------- catálogo
    print("\n[2] Catálogo de produtos")
    produtos = SupabaseProductRepository(client, sessao.company_id, role=sessao.role)
    try:
        catalogo = produtos.load_catalog()
        print(f"  {OK} {len(catalogo)} produto(s) legível(is) pela RLS da empresa")
        for produto in list(catalogo.values())[:5]:
            print(f"      {produto.code}  {produto.name[:28]:<28} "
                  f"{produto.sale_price:>12}  est. {produto.stock:>4}  {produto.stock_status}")
        if not catalogo:
            print(f"  {AVISO} vazio: ou a empresa não tem produtos, ou a RLS não "
                  f"reconhece o vínculo (confira company_users).")
        print(f"  {OK} próximo código sugerido: {produtos.next_code()}")
        categorias = produtos.list_active_categories()
        print(f"  {OK} categorias: {', '.join(categorias) if categorias else '(nenhuma)'}")
        if not categorias:
            print(f"  {AVISO} sem categoria, todo cadastro de produto será recusado "
                  f"por 'Item category doesnt exist'.")
    except Exception as erro:
        print(f"  {FALHA} {type(erro).__name__}: {erro}")
        falhas.append("catálogo")

    # -------------------------------------------------------------- usuários
    print("\n[3] Diretório de usuários")
    usuarios = SupabaseUserRepository(client, sessao.company_id, role=sessao.role)
    try:
        linhas = usuarios.list_users()
        print(f"  {OK} {len(linhas)} usuário(s)")
        for nome, login, depto, perfil, status, acesso, _cor in linhas:
            print(f"      {nome[:18]:<18} {login[:28]:<28} {depto[:12]:<12} "
                  f"{perfil:<14} {status:<9} {acesso}")
    except Exception as erro:
        texto = str(getattr(erro, "message", erro))
        if "could not find the function" in texto.lower():
            print(f"  {FALHA} fn_list_company_users não existe com esta assinatura.")
            print("      Falta aplicar 20261004090000_user_directory.sql.")
        elif str(sessao.role) != "ADMIN":
            print(f"  {OK} recusado para o papel {sessao.role} — esperado, "
                  f"só ADMIN lista usuários")
            texto = None
        else:
            print(f"  {FALHA} {type(erro).__name__}: {texto}")
        if texto is not None:
            falhas.append("usuários")

    # ------------------------------------------------------------- resultado
    print("\n" + "=" * 60)
    if falhas:
        print(f"{FALHA} Com problema: {', '.join(falhas)}")
        print("  Para ver o que o banco tem de fato: scripts/verificar_migrations.sql")
        return 1

    print(f"{OK} Caminho de banco funcionando ponta a ponta.")
    print("  Rode a aplicação com:  STOCKFLOW_BACKEND=supabase uv run stockflow")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        # Encerra a sessão para não deixar refresh token válido em disco.
        try:
            get_client().auth.sign_out()
        except Exception:
            pass

"""Diagnóstico da conexão com o Supabase e do que a aplicação precisa dele.

    uv run python scripts/test_supabase_connection.py

Checa como ANÔNIMO, que é tudo o que a chave publicável permite sem login.
Para exercitar o caminho autenticado (o que a aplicação realmente faz), use
`scripts/verificar_login.py`, que pede as credenciais.

NADA ACONTECE NO IMPORT, de propósito. O nome começa com `test_`, então o
`pytest` varre este arquivo ao rodar sem caminho; com a consulta solta no
corpo do módulo, a COLETA da suíte inteira morria aqui.

LEIA O VEREDITO COM CUIDADO: depois da migration de identidade por JWT,
"permission denied" para o anônimo é a resposta CERTA, não um problema. A
allowlist é concedida a `authenticated`, nunca a `anon` — se o anônimo
conseguisse executar, aí sim haveria falha de segurança. O que distingue
"função existe e recusa" de "função não existe" é a mensagem, e é isso que
este script separa.
"""

import sys

from stockflow.infrastructure.database.supabase_client import get_client, is_configured

EXISTE = "existe"
AUSENTE = "ausente"
ABERTA = "aberta"

# Funções que a aplicação chama, com argumentos válidos para que o PostgREST
# resolva a assinatura. Os uuids são de descarte: nenhuma chega a executar
# como anônimo.
VAZIO = "00000000-0000-0000-0000-000000000000"
FUNCOES = (
    ("fn_current_user_id", {}, "login"),
    ("fn_my_companies", {}, "login"),
    ("fn_create_products", {"p_company_id": VAZIO, "p_barcode": "x",
                            "p_name": "x", "p_sell_price": 1}, "catálogo"),
    ("fn_update_products", {"p_product_id": VAZIO}, "catálogo"),
    ("fn_set_product_active", {"p_product_id": VAZIO, "p_active": True}, "catálogo"),
    ("fn_set_min_stock", {"p_product_id": VAZIO, "p_min": 1}, "catálogo"),
    ("fn_list_company_users", {"p_company_id": VAZIO}, "usuários"),
    ("fn_set_company_user_department", {"p_company_id": VAZIO, "p_user_id": VAZIO,
                                        "p_department": "x"}, "usuários"),
)

TABELAS = ("products", "categories", "product_stock", "company")


def _estado(erro) -> str:
    mensagem = str(getattr(erro, "message", erro)).lower()
    if "could not find the function" in mensagem or "could not find the table" in mensagem:
        return AUSENTE
    if "permission denied" in mensagem:
        return EXISTE
    return mensagem[:60]


def main() -> int:
    if not is_configured():
        print("✗ SUPABASE_URL / SUPABASE_PUBLISHABLE_KEY ausentes.")
        print("  Copie .env.example para .env e preencha.")
        return 1

    client = get_client()
    print("Checando como ANÔNIMO (chave publicável, sem login).\n")

    print("Tabelas:")
    problemas = []
    for tabela in TABELAS:
        try:
            client.table(tabela).select("*").limit(1).execute()
            print(f"  ⚠ {tabela:<16} LEITURA ABERTA sem login — a RLS deveria recusar")
            problemas.append(f"{tabela} legível por anônimo")
        except Exception as erro:
            estado = _estado(erro)
            if estado == EXISTE:
                print(f"  ✓ {tabela:<16} existe, RLS recusa o anônimo")
            else:
                print(f"  ✗ {tabela:<16} {estado}")
                problemas.append(f"tabela {tabela}: {estado}")

    print("\nFunções da aplicação:")
    faltando = []
    for nome, args, grupo in FUNCOES:
        try:
            client.rpc(nome, args).execute()
            print(f"  ⚠ {nome:<32} EXECUTOU como anônimo — não deveria")
            problemas.append(f"{nome} executável por anônimo")
        except Exception as erro:
            estado = _estado(erro)
            if estado == EXISTE:
                print(f"  ✓ {nome:<32} existe  ({grupo})")
            elif estado == AUSENTE:
                print(f"  ✗ {nome:<32} NÃO EXISTE  ({grupo})")
                faltando.append((nome, grupo))
            else:
                print(f"  ? {nome:<32} {estado}")

    print()
    if faltando:
        grupos = {grupo for _, grupo in faltando}
        print("→ Funções ausentes:", ", ".join(nome for nome, _ in faltando))
        if "usuários" in grupos:
            print("  Falta 20261004090000_user_directory.sql (tela de Usuários).")
        if "catálogo" in grupos or "login" in grupos:
            print("  Falta 20261003180000_auth_jwt_identity.sql, ou as funções do")
            print("  catálogo nunca foram criadas neste projeto.")
        print("  Confira o que o banco realmente tem com scripts/verificar_migrations.sql.")
        return 1

    if problemas:
        print("→ Atenção:", "; ".join(problemas))
        return 1

    print("✓ Todas as funções existem e recusam o anônimo — que é o esperado.")
    print("  A permissão de EXECUTE é concedida a `authenticated`, não a `anon`,")
    print("  então este script NÃO consegue provar que o login funciona.")
    print("  Para isso: uv run python scripts/verificar_login.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Verifica as procedures/funções criadas pelas migrations desta branch.

NÃO é executado automaticamente: ele GRAVA dados no Supabase real.
Rode você mesmo, de propósito, a partir da raiz do projeto:

    uv run python scripts/verificar_procedures.py

O script cria uma categoria e um produto com nomes marcados como
`__TESTE__`, confere o resultado e remove tudo no final.

As funções são SECURITY DEFINER e checam fn_has_role, então a sessão precisa
estar autenticada e STOCKFLOW_TEST_COMPANY_ID precisa apontar para uma empresa
onde o usuário seja ADMIN ou STOCK:

    STOCKFLOW_TEST_COMPANY_ID=<uuid> uv run python scripts/verificar_procedures.py
"""

import os
import sys

from stockflow.infrastructure.database.supabase_client import supabase

MARCA = "__TESTE__"
COMPANY_ID = os.getenv("STOCKFLOW_TEST_COMPANY_ID")
categoria_id = None
produto_id = None


def passo(nome, fn):
    try:
        resultado = fn()
        print(f"OK      {nome}")
        return resultado
    except Exception as exc:
        print(f"FALHOU  {nome}: {getattr(exc, 'message', exc)}")
        return None


def main():
    global categoria_id, produto_id

    if not COMPANY_ID:
        sys.exit(
            "defina STOCKFLOW_TEST_COMPANY_ID com o uuid da empresa de teste; "
            "categories e products são multi-tenant e company_id é obrigatório"
        )

    categoria_id = passo(
        "fn_create_categories cria categoria",
        lambda: supabase.rpc("fn_create_categories", {"p_company_id": COMPANY_ID, "p_name": f"{MARCA} Periféricos"}).execute().data,
    )

    passo(
        "fn_create_categories recusa categoria duplicada",
        lambda: _espera_erro(
            lambda: supabase.rpc("fn_create_categories", {"p_company_id": COMPANY_ID, "p_name": f"{MARCA} Periféricos"}).execute(),
            "Category already exists",
        ),
    )

    produto_id = passo(
        "fn_create_products cria produto na categoria",
        lambda: supabase.rpc(
            "fn_create_products",
            {
                "p_company_id": COMPANY_ID,
                "p_barcode": f"{MARCA}-0001",
                "p_name": f"{MARCA} Mouse ergonômico",
                "p_sell_price": 189.90,
                "p_buy_price": 120.00,
                "p_unit": "UN",
                "p_stock": 2,
                "p_item_category": f"{MARCA} Periféricos",
            },
        ).execute().data,
    )

    passo(
        "fn_create_products recusa categoria inexistente",
        lambda: _espera_erro(
            lambda: supabase.rpc(
                "fn_create_products",
                {
                    "p_company_id": COMPANY_ID,
                    "p_barcode": f"{MARCA}-0002",
                    "p_name": f"{MARCA} Teclado",
                    "p_sell_price": 459.90,
                    "p_item_category": "categoria-que-nao-existe",
                },
            ).execute(),
            "Item category doesnt exist",
        ),
    )

    passo(
        "products.stock recusa valor negativo (CHECK)",
        lambda: _espera_erro(
            lambda: supabase.rpc(
                "fn_create_products",
                {
                    "p_company_id": COMPANY_ID,
                    "p_barcode": f"{MARCA}-0003",
                    "p_name": f"{MARCA} Cabo",
                    "p_sell_price": 29.90,
                    "p_stock": -5,
                },
            ).execute(),
            "check",
        ),
    )

    passo(
        "pr_validate_login responde sem erro de coluna",
        lambda: supabase.rpc("pr_validate_login", {"v_name": MARCA, "pass": "x"}).execute().data,
    )


def _espera_erro(fn, trecho):
    try:
        fn()
    except Exception as exc:
        mensagem = str(getattr(exc, "message", exc))
        if trecho.lower() in mensagem.lower():
            return mensagem
        raise AssertionError(f"erro diferente do esperado: {mensagem}") from exc
    raise AssertionError(f"esperava erro contendo {trecho!r}, mas passou")


def limpar():
    print("\nLimpando dados de teste...")
    try:
        # Escopado à empresa de teste: o mesmo nome pode existir em outra.
        supabase.table("products").delete().eq(
            "company_id", COMPANY_ID
        ).like("name", f"{MARCA}%").execute()
        supabase.table("categories").delete().eq(
            "company_id", COMPANY_ID
        ).like("name", f"{MARCA}%").execute()
        print("OK      dados de teste removidos")
    except Exception as exc:
        print(f"FALHOU  limpeza: {getattr(exc, 'message', exc)}")
        print("        remova manualmente as linhas com nome iniciando em __TESTE__")


if __name__ == "__main__":
    try:
        main()
    finally:
        limpar()

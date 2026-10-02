"""Verifica as procedures/funções criadas pelas migrations desta branch.

NÃO é executado automaticamente: ele GRAVA dados no Supabase real.
Rode você mesmo, de propósito, a partir da raiz do projeto:

    uv run python scripts/verificar_procedures.py

O script cria uma categoria e um produto com nomes marcados como
`__TESTE__`, confere o resultado e remove tudo no final.
"""

from stockflow.infrastructure.database.supabase_client import supabase

MARCA = "__TESTE__"
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

    categoria_id = passo(
        "create_categories cria categoria",
        lambda: supabase.rpc("create_categories", {"p_name": f"{MARCA} Periféricos"}).execute().data,
    )

    passo(
        "create_categories recusa categoria duplicada",
        lambda: _espera_erro(
            lambda: supabase.rpc("create_categories", {"p_name": f"{MARCA} Periféricos"}).execute(),
            "Category already exists",
        ),
    )

    produto_id = passo(
        "create_products cria produto na categoria",
        lambda: supabase.rpc(
            "create_products",
            {
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
        "create_products recusa categoria inexistente",
        lambda: _espera_erro(
            lambda: supabase.rpc(
                "create_products",
                {
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
                "create_products",
                {
                    "p_barcode": f"{MARCA}-0003",
                    "p_name": f"{MARCA} Cabo",
                    "p_sell_price": 29.90,
                    "p_stock": -5,
                },
            ).execute(),
            "check",
        ),
    )

    # validate_login tem bug conhecido: faz SELECT password, mas a coluna
    # da tabela access_register se chama pass_hash.
    passo(
        "validate_login responde sem erro de coluna",
        lambda: supabase.rpc("validate_login", {"v_name": MARCA, "pass": "x"}).execute().data,
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
        supabase.table("products").delete().like("name", f"{MARCA}%").execute()
        supabase.table("categories").delete().like("name", f"{MARCA}%").execute()
        print("OK      dados de teste removidos")
    except Exception as exc:
        print(f"FALHOU  limpeza: {getattr(exc, 'message', exc)}")
        print("        remova manualmente as linhas com nome iniciando em __TESTE__")


if __name__ == "__main__":
    try:
        main()
    finally:
        limpar()

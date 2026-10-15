from stockflow.infrastructure.database.supabase_client import supabase

def test_adjustment():
    # IDs de teste 
    COMPANY_ID = 'ID_DA_EMPRESA'
    PRODUCT_ID = 'ID_DO_PRODUTO'
    USER_ID = 'ID_DO_USUARIO(ADM)'

    # Passo 0: Consultar saldo inicial
    try:
        prod_res = supabase.table("products").select("name, stock").eq("id", PRODUCT_ID).execute()
        if not prod_res.data:
            print(f" Produto {PRODUCT_ID} não encontrado.")
            return
        saldo_inicial = prod_res.data[0]["stock"]
        print(f" Produto: {prod_res.data[0]['name']} | Saldo inicial: {saldo_inicial}")
    except Exception as e:
        print(f" Erro ao consultar produto inicial: {e}")
        return

    # -------------------------------------------------------------
    # Cenário 1: Ajuste Válido (Entrada com justificativa)
    # -------------------------------------------------------------
    print("\n--- Cenário 1: Ajuste Válido (Entrada) ---")
    qtd_entrada = 5
    try:
        supabase.rpc('fn_adjust_product_stock', {
            'p_product_id': PRODUCT_ID,
            'p_company_id': COMPANY_ID,
            'p_quantity': qtd_entrada,
            'p_movement_kind': 'ENTRADA',
            'p_justification': 'Ajuste manual de inventário - conferência física',
            'p_user_id': USER_ID
        }).execute()

        # Verifica se o saldo aumentou
        saldo_pos_entrada = supabase.table("products").select("stock").eq("id", PRODUCT_ID).execute().data[0]["stock"]
        if saldo_pos_entrada == saldo_inicial + qtd_entrada:
            print(f" Sucesso: Saldo atualizado atomicamente de {saldo_inicial} para {saldo_pos_entrada}.")
        else:
            print(f" ERRO: Saldo esperado {saldo_inicial + qtd_entrada}, mas está em {saldo_pos_entrada}!")

        # Verifica se o histórico gravou a justificativa
        mov = supabase.table("stock_movements").select("note, status").eq("product_id", PRODUCT_ID).order("created_on", desc=True).limit(1).execute().data[0]
        print(f" Rastreabilidade: Movimentação gravada com status '{mov['status']}' e nota: '{mov['note']}'")
    except Exception as e:
        print(f" Erro inesperado no Cenário 1: {e}")

    print("\n--- Cenário 2: Ajuste Inválido (Sem Justificativa) ---")
    try:
        supabase.rpc('fn_adjust_product_stock', {
            'p_product_id': PRODUCT_ID,
            'p_company_id': COMPANY_ID,
            'p_quantity': 2,
            'p_movement_kind': 'ENTRADA',
            'p_justification': '   ',  # Em branco
            'p_user_id': USER_ID
        }).execute()
        print("ERRO: O banco permitiu ajuste sem justificativa!")
    except Exception as e:
        print(f" Sucesso: Banco recusou ajuste sem justificativa ({e})")

    # -------------------------------------------------------------
    # Cenário 3: Ajuste Inválido (Saldo Negativo)
    # -------------------------------------------------------------
    print("\n--- Cenário 3: Ajuste Inválido (Saldo Negativo) ---")
    saldo_atual = supabase.table("products").select("stock").eq("id", PRODUCT_ID).execute().data[0]["stock"]
    qtd_saida_excessiva = saldo_atual + 500
    try:
        supabase.rpc('fn_adjust_product_stock', {
            'p_product_id': PRODUCT_ID,
            'p_company_id': COMPANY_ID,
            'p_quantity': qtd_saida_excessiva,
            'p_movement_kind': 'SAIDA',
            'p_justification': 'Tentativa de ajuste para saldo negativo',
            'p_user_id': USER_ID
        }).execute()
        print(" ERRO: O banco permitiu saldo negativo!")
    except Exception as e:
        print(f" Sucesso: Banco bloqueou saldo negativo ({e})")

    # -------------------------------------------------------------
    # Cenário 4: Atomicidade (Garantir que falhas não alteraram nada)
    # -------------------------------------------------------------
    saldo_final = supabase.table("products").select("stock").eq("id", PRODUCT_ID).execute().data[0]["stock"]
    if saldo_final == saldo_atual:
        print(f"\n Atomicidade garantida: Saldo final ({saldo_final}) permaneceu intacto após as recusas.")
    else:
        print(f"\n Falha de integridade: Saldo mudou para {saldo_final} após operações inválidas.")

if __name__ == "__main__":
    test_adjustment()
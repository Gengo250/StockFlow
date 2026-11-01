from uuid import uuid4


def test_history_lists_final_sales_by_default_and_pending_when_filtered(
    db_tx, create_company
):
    client_id = uuid4()
    db_tx.execute("RESET ROLE")
    db_tx.execute(
        "INSERT INTO public.clients (id, company_id, name) "
        "VALUES (%s, %s, 'Cliente de teste')",
        (client_id, create_company),
    )
    for status in ("CONCLUIDA", "CANCELADA", "DEVOLVIDA", "PENDENTE"):
        # `created_by` vem de fn_current_user_id(), que é a MESMA origem que a
        # aplicação usa para carimbar o autor da venda. Informar aqui não é
        # detalhe de teste: a coluna é obrigatória, e omiti-la montava uma
        # venda que nenhum caminho real produz.
        db_tx.execute(
            "INSERT INTO public.sales "
            "(id, company_id, client_id, client_name, total, status, created_by) "
            "VALUES (%s, %s, %s, 'Cliente de teste', 10, %s::public.sale_status, "
            "public.fn_current_user_id())",
            (uuid4(), create_company, client_id, status),
        )
    db_tx.execute("SET LOCAL ROLE authenticated")

    padrao = {
        row[0]
        for row in db_tx.execute(
            "SELECT status::text FROM public.fn_list_sales(%s, p_limit => 50)",
            (create_company,),
        ).fetchall()
    }
    pendentes = {
        row[0]
        for row in db_tx.execute(
            "SELECT status::text FROM public.fn_list_sales("
            "%s, p_status => 'PENDENTE', p_limit => 50)",
            (create_company,),
        ).fetchall()
    }

    assert padrao == {"CONCLUIDA", "CANCELADA", "DEVOLVIDA"}
    assert pendentes == {"PENDENTE"}

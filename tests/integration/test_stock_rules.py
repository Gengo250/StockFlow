import pytest
import uuid

@pytest.mark.asyncio
async def test_set_max_stock_respects_company_limit(db_tx, create_company):
    """Cenário: Tentar definir estoque máximo maior que o teto da empresa."""
    product_id = uuid.uuid4()
    await db_tx.execute(
        "INSERT INTO public.products (id, company_id, name, stock) VALUES ($1, $2, $3, $4)",
        product_id, create_company, "Produto Teste", 100
    )
    await db_tx.execute(
        "INSERT INTO public.product_stock (product_id, min_quantity) VALUES ($1, $2)",
        product_id, 10
    )

    # Tenta definir max = 15000 (acima do teto padrão da empresa)
    with pytest.raises(Exception) as exc:
        await db_tx.execute(
            "SELECT public.fn_set_max_stock($1, $2)",
            product_id, 15000
        )
    assert any(term in str(exc.value).lower() for term in ["excede o teto", "excede o limite global"])


@pytest.mark.asyncio
async def test_max_cannot_be_less_than_current_stock(db_tx, create_company):
    """Cenário: Tentar definir máximo menor que o saldo atual."""
    product_id = uuid.uuid4()
    await db_tx.execute(
        "INSERT INTO public.products (id, company_id, name, stock) VALUES ($1, $2, $3, $4)",
        product_id, create_company, "Produto Teste", 400
    )
    await db_tx.execute(
        "INSERT INTO public.product_stock (product_id, min_quantity) VALUES ($1, $2)",
        product_id, 10
    )

    # Tenta definir max = 300 (menor que o saldo 400)
    with pytest.raises(Exception) as exc:
        await db_tx.execute(
            "SELECT public.fn_set_max_stock($1, $2)",
            product_id, 300
        )
    assert any(term in str(exc.value).lower() for term in ["não pode ser menor que o saldo", "menor que o saldo atual"])


@pytest.mark.asyncio
async def test_set_company_max_stock_limit_ok(db_tx, create_company):
    """Cenário Happy-Path: Administrador altera o teto global da empresa com sucesso."""
    await db_tx.execute(
        "SELECT public.fn_set_company_max_stock_limit($1, $2)",
        create_company, 25000
    )
    novo_limite = await db_tx.fetchval(
        "SELECT max_stock_limit FROM public.company WHERE id = $1",
        create_company
    )
    assert novo_limite == 25000


@pytest.mark.asyncio
async def test_set_company_max_stock_limit_negative(db_tx, create_company):
    """Cenário: Rejeitar limite global da empresa com valor negativo."""
    with pytest.raises(Exception) as exc:
        await db_tx.execute(
            "SELECT public.fn_set_company_max_stock_limit($1, $2)",
            create_company, -100
        )
    assert any(term in str(exc.value).lower() for term in ["negativo", "maior ou igual a zero"])


@pytest.mark.asyncio
async def test_set_company_max_stock_limit_blocked_by_product_max(db_tx, create_company):
    """Cenário: Impossibilidade de reduzir o teto da empresa abaixo de um produto já cadastrado com max_quantity superior."""
    product_id = uuid.uuid4()
    await db_tx.execute(
        "INSERT INTO public.products (id, company_id, name, stock) VALUES ($1, $2, $3, $4)",
        product_id, create_company, "Produto Teto Alto", 100
    )
    await db_tx.execute(
        "INSERT INTO public.product_stock (product_id, min_quantity, max_quantity) VALUES ($1, $2, $3)",
        product_id, 10, 5000
    )

    # Tenta reduzir o teto da empresa para 3000 (abaixo de 5000)
    with pytest.raises(Exception) as exc:
        await db_tx.execute(
            "SELECT public.fn_set_company_max_stock_limit($1, $2)",
            create_company, 3000
        )
    assert any(term in str(exc.value).lower() for term in ["produtos com estoque máximo superior", "não é possível definir o teto"])


@pytest.mark.asyncio
async def test_get_effective_max_stock_uses_product_max(db_tx, create_company):
    """Cenário: fn_get_effective_max_stock retorna max_quantity quando o produto possui limite individual."""
    product_id = uuid.uuid4()
    await db_tx.execute(
        "INSERT INTO public.products (id, company_id, name, stock) VALUES ($1, $2, $3, $4)",
        product_id, create_company, "Produto Individual", 10
    )
    await db_tx.execute(
        "INSERT INTO public.product_stock (product_id, min_quantity, max_quantity) VALUES ($1, $2, $3)",
        product_id, 5, 80
    )

    efetivo = await db_tx.fetchval(
        "SELECT public.fn_get_effective_max_stock($1)",
        product_id
    )
    assert efetivo == 80


@pytest.mark.asyncio
async def test_get_effective_max_stock_uses_company_limit(db_tx, create_company):
    """Cenário: fn_get_effective_max_stock faz fallback para o teto da empresa quando o produto não tem limite configurado."""
    product_id = uuid.uuid4()
    await db_tx.execute(
        "INSERT INTO public.products (id, company_id, name, stock) VALUES ($1, $2, $3, $4)",
        product_id, create_company, "Produto Sem Teto Próprio", 10
    )
    # Tabela product_stock com max_quantity NULL
    await db_tx.execute(
        "INSERT INTO public.product_stock (product_id, min_quantity, max_quantity) VALUES ($1, $2, $3)",
        product_id, 5, None
    )

    teto_empresa = await db_tx.fetchval(
        "SELECT max_stock_limit FROM public.company WHERE id = $1",
        create_company
    )
    efetivo = await db_tx.fetchval(
        "SELECT public.fn_get_effective_max_stock($1)",
        product_id
    )
    assert efetivo == teto_empresa


@pytest.mark.asyncio
async def test_movement_exceeds_max_fails(db_tx, create_company):
    """Cenário: Trigger trg_stock_movements_apply deve abortar movimentação cujo saldo final ultrapasse o limite."""
    product_id = uuid.uuid4()
    await db_tx.execute(
        "INSERT INTO public.products (id, company_id, name, stock) VALUES ($1, $2, $3, $4)",
        product_id, create_company, "Produto Para Teste de Trigger", 20
    )
    await db_tx.execute(
        "INSERT INTO public.product_stock (product_id, min_quantity, max_quantity) VALUES ($1, $2, $3)",
        product_id, 5, 50
    )

    # Tenta registrar uma entrada confirmada de 40 unidades (saldo iria para 60 > 50)
    with pytest.raises(Exception) as exc:
        await db_tx.execute(
            """INSERT INTO public.stock_movements (company_id, product_id, kind, quantity, status, confirmed_on)
               VALUES ($1, $2, 'ENTRADA', 40, 'CONFIRMADA', now())""",
            create_company, product_id
        )
    assert any(term in str(exc.value).lower() for term in ["ultrapassaria o estoque máximo", "movimentação rejeitada"])


@pytest.mark.asyncio
async def test_set_max_stock_happy_path(db_tx, create_company):
    """Cenário Happy-Path: Define um estoque máximo válido para o produto."""
    product_id = uuid.uuid4()
    await db_tx.execute(
        "INSERT INTO public.products (id, company_id, name, stock) VALUES ($1, $2, $3, $4)",
        product_id, create_company, "Produto Válido", 30
    )
    await db_tx.execute(
        "INSERT INTO public.product_stock (product_id, min_quantity) VALUES ($1, $2)",
        product_id, 10
    )

    # Define max_quantity = 500 (válido: >= min(10), >= stock(30) e <= company(10000))
    await db_tx.execute(
        "SELECT public.fn_set_max_stock($1, $2)",
        product_id, 500
    )

    max_salvo = await db_tx.fetchval(
        "SELECT max_quantity FROM public.product_stock WHERE product_id = $1",
        product_id
    )
    assert max_salvo == 500

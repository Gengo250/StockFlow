-- Fecha as divergências em que o banco implantado está ATRÁS da fonte
-- declarativa. As divergências de sentido oposto (onde o declarativo estava
-- atrás) foram resolvidas no próprio `database/code/`, sem migration, porque
-- ali o banco já era a verdade.
--
-- Três objetos, e nenhum deles muda dado:
--
--   1. sales_company_id_client_id_fkey — a ação de exclusão volta a ser
--      RESTRICT. Não é preferência: cliente com venda no histórico não pode
--      ser apagado, e `tests/test_clientes_database_contract.py` cobra essa
--      ação por nome. O banco ficou com SET NULL quando `sales` foi recriada
--      em 20261010231302, e ninguém reconciliou depois.
--
--   2. product_stock_max_quantity_check — a guarda existe em
--      `code/tables/04_stock.sql` e nunca chegou ao banco.
--
--   3. sale_items_quantity_check — mesma regra dos dois lados, mas o banco
--      guarda a versão com conversão para numeric, herdada de quando a coluna
--      era numeric(10,3). Hoje é integer, e a conversão só atrapalha a
--      comparação entre os dois caminhos.
--
-- Fora do escopo, de propósito: a sobrecarga órfã de três argumentos de
-- `fn_edit_product_stock`, aposentada pela versão de quatro argumentos e já
-- com EXECUTE revogado. Removê-la aqui faria
-- `test_schema_declarativo.py::test_code_nao_inventa_objetos_fora_das_migrations`
-- falhar: aquele teste rastreia objeto por NOME, sem assinatura, então um
-- DROP de uma sobrecarga parece a remoção da função inteira. Afrouxar um
-- teste de guarda para acomodar esta migration seria o caminho errado; a
-- remoção espera o teste aprender a distinguir assinaturas.
--
-- As duas trocas de restrição tomam lock exclusivo breve em `sales`,
-- `clients`, `sale_items` e `product_stock`. No tamanho deste banco é
-- instantâneo.

BEGIN;

-- 1. Exclusão de cliente volta a ser bloqueada por venda no histórico.
--
-- Recriar a chave estrangeira revalida as linhas existentes, então a
-- conferência vem antes: uma venda apontando para cliente inexistente faria a
-- migration falhar com mensagem genérica de violação, e o que o operador
-- precisa saber é QUANTAS linhas estão órfãs.
DO $$
DECLARE
    v_orfas integer;
BEGIN
    SELECT count(*) INTO v_orfas
      FROM public.sales s
     WHERE s.client_id IS NOT NULL
       AND NOT EXISTS (
           SELECT 1
             FROM public.clients c
            WHERE c.company_id = s.company_id
              AND c.id = s.client_id
       );

    IF v_orfas > 0 THEN
        RAISE EXCEPTION
            'sales tem % linha(s) apontando para cliente inexistente; corrija o dado antes de aplicar esta migration',
            v_orfas;
    END IF;
END;
$$;

ALTER TABLE public.sales
    DROP CONSTRAINT IF EXISTS sales_company_id_client_id_fkey;

ALTER TABLE public.sales
    ADD CONSTRAINT sales_company_id_client_id_fkey
        FOREIGN KEY (company_id, client_id)
        REFERENCES public.clients (company_id, id) ON DELETE RESTRICT;

-- 2. Saldo máximo não negativo.
--
-- Linha negativa aqui seria bug de gravação, não dado legítimo; mesmo assim a
-- falha precisa dizer quantas são, e não só "check constraint is violated".
DO $$
DECLARE
    v_invalidas integer;
BEGIN
    SELECT count(*) INTO v_invalidas
      FROM public.product_stock
     WHERE max_quantity IS NOT NULL AND max_quantity < 0;

    IF v_invalidas > 0 THEN
        RAISE EXCEPTION
            'product_stock tem % linha(s) com max_quantity negativo; corrija o dado antes de aplicar esta migration',
            v_invalidas;
    END IF;
END;
$$;

ALTER TABLE public.product_stock
    ADD CONSTRAINT product_stock_max_quantity_check CHECK (max_quantity >= 0);

-- 3. Quantidade do item de venda, sem a conversão herdada.
--
-- Mesma semântica, nome igual: a restrição é recriada para que os dois
-- caminhos produzam o mesmo texto, e não para mudar o que ela proíbe.
ALTER TABLE public.sale_items
    DROP CONSTRAINT IF EXISTS sale_items_quantity_check;

ALTER TABLE public.sale_items
    ADD CONSTRAINT sale_items_quantity_check CHECK (quantity > 0);

-- Conferência final. Declarar sucesso sem olhar o resultado é o mesmo que não
-- ter conferência nenhuma.
DO $$
DECLARE
    v_acao_fk text;
BEGIN
    SELECT confdeltype INTO v_acao_fk
      FROM pg_constraint
     WHERE conname = 'sales_company_id_client_id_fkey';

    -- 'r' é RESTRICT no catálogo do PostgreSQL; 'n' seria SET NULL.
    IF v_acao_fk IS DISTINCT FROM 'r' THEN
        RAISE EXCEPTION 'sales_company_id_client_id_fkey não ficou como RESTRICT (valor: %)', v_acao_fk;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'product_stock_max_quantity_check'
    ) THEN
        RAISE EXCEPTION 'product_stock_max_quantity_check não foi criada';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'sale_items_quantity_check'
    ) THEN
        RAISE EXCEPTION 'sale_items_quantity_check não foi recriada';
    END IF;
END;
$$;

COMMIT;

-- Sondagem ANTES de aplicar 20261024120000_us17_sales_history.sql.
--
-- SOMENTE LEITURA: nenhum comando aqui cria, altera ou remove nada. Pode ser
-- colado no SQL Editor do Supabase ou rodado por psql.
--
-- Por que existe: o banco remoto deste projeto NÃO nasceu das migrations
-- (`sales` e `sale_items` chegaram lá por outro caminho). Aplicar a migration
-- da US17 supondo a cadeia inteira pode falhar no meio, e migration que falha
-- pela metade em produção é o estado mais caro de consertar.
--
-- Leia a coluna `situacao`. Se TUDO estiver "ok", a migration tem o terreno
-- de que precisa. Qualquer "FALTA" é bloqueio: pare e me mostre o resultado.

WITH esperado(ordem, objeto, descricao, existe) AS (
    VALUES
    -- Tipos de que a migration depende -------------------------------------
    (1, 'type public.sale_status',
        'Enum de situação da venda; a migration ACRESCENTA DEVOLVIDA a ele',
        EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
                 WHERE n.nspname = 'public' AND t.typname = 'sale_status')),
    (2, 'type public.payment_method',
        'Usado na assinatura de fn_list_sales',
        EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
                 WHERE n.nspname = 'public' AND t.typname = 'payment_method')),
    (3, 'type public.user_role',
        'Usado no ARRAY[ADMIN] das funções de reversão',
        EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
                 WHERE n.nspname = 'public' AND t.typname = 'user_role')),

    -- Tabelas ---------------------------------------------------------------
    (4, 'table public.sales',
        'Alvo da FK de sale_reversals',
        to_regclass('public.sales') IS NOT NULL),
    (5, 'table public.sale_items',
        'fn_list_sales agrega os itens a partir dela',
        to_regclass('public.sale_items') IS NOT NULL),
    (6, 'table public.user_accounts',
        'fn_list_sales faz LEFT JOIN para o nome do vendedor',
        to_regclass('public.user_accounts') IS NOT NULL),
    (7, 'table public.stock_movements',
        'As duas funções de reversão escrevem nela',
        to_regclass('public.stock_movements') IS NOT NULL),

    -- Colunas que as funções leem ------------------------------------------
    (8, 'sales.created_by',
        'Vira seller_id no histórico e autor no vínculo',
        EXISTS (SELECT 1 FROM information_schema.columns
                 WHERE table_schema = 'public' AND table_name = 'sales'
                   AND column_name = 'created_by')),
    (9, 'sales.payment_method',
        'Coluna devolvida pelo histórico',
        EXISTS (SELECT 1 FROM information_schema.columns
                 WHERE table_schema = 'public' AND table_name = 'sales'
                   AND column_name = 'payment_method')),
    (10, 'sales.discount',
        'Coluna devolvida pelo histórico',
        EXISTS (SELECT 1 FROM information_schema.columns
                 WHERE table_schema = 'public' AND table_name = 'sales'
                   AND column_name = 'discount')),
    (11, 'user_accounts.name',
        'Nome do vendedor e de quem reverteu',
        EXISTS (SELECT 1 FROM information_schema.columns
                 WHERE table_schema = 'public' AND table_name = 'user_accounts'
                   AND column_name = 'name')),
    (12, 'stock_movements.sale_id',
        'Liga a movimentação à venda; sem ela a reversão não acha o que desfazer',
        EXISTS (SELECT 1 FROM information_schema.columns
                 WHERE table_schema = 'public' AND table_name = 'stock_movements'
                   AND column_name = 'sale_id')),

    -- Constraint exigida pela FK composta -----------------------------------
    (13, 'unique (company_id, id) em public.sales',
        'sale_reversals referencia esse par; sem ele a FK não cria',
        EXISTS (SELECT 1 FROM pg_constraint c
                 WHERE c.conrelid = 'public.sales'::regclass
                   AND c.contype IN ('u', 'p')
                   AND (SELECT array_agg(a.attname::text ORDER BY a.attname)
                          FROM unnest(c.conkey) k
                          JOIN pg_attribute a
                            ON a.attrelid = c.conrelid AND a.attnum = k)
                       = ARRAY['company_id', 'id'])),

    -- Funções auxiliares ----------------------------------------------------
    (14, 'function public.fn_is_member',
        'fn_list_sales repete a checagem de RLS com ela',
        EXISTS (SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
                 WHERE n.nspname = 'public' AND p.proname = 'fn_is_member')),
    (15, 'function public.fn_has_role',
        'Alçada de ADMIN nas funções de reversão',
        EXISTS (SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
                 WHERE n.nspname = 'public' AND p.proname = 'fn_has_role')),
    (16, 'function public.fn_current_user_id',
        'Autor da reversão',
        EXISTS (SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
                 WHERE n.nspname = 'public' AND p.proname = 'fn_current_user_id')),

    -- Role ------------------------------------------------------------------
    (17, 'role app_backend',
        'Recebe GRANT SELECT na tabela nova',
        EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_backend'))
)
SELECT ordem,
       objeto,
       CASE WHEN existe THEN 'ok' ELSE '>>> FALTA <<<' END AS situacao,
       descricao
  FROM esperado
 ORDER BY ordem;

-- ---------------------------------------------------------------------------
-- Já foi aplicada? Rode também isto. Tudo "ja existe" significa que a
-- migration já passou por aqui e reaplicá-la não muda nada.
-- ---------------------------------------------------------------------------

WITH depois(objeto, existe) AS (
    VALUES
    ('valor DEVOLVIDA em sale_status',
        EXISTS (SELECT 1 FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid
                 WHERE t.typname = 'sale_status' AND e.enumlabel = 'DEVOLVIDA')),
    ('type public.sale_reversal_kind',
        EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
                 WHERE n.nspname = 'public' AND t.typname = 'sale_reversal_kind')),
    ('table public.sale_reversals',
        to_regclass('public.sale_reversals') IS NOT NULL),
    ('policy sale_reversals_select',
        EXISTS (SELECT 1 FROM pg_policy p JOIN pg_class c ON c.oid = p.polrelid
                 WHERE c.relname = 'sale_reversals' AND p.polname = 'sale_reversals_select')),
    ('function public.fn_list_sales',
        EXISTS (SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
                 WHERE n.nspname = 'public' AND p.proname = 'fn_list_sales')),
    ('function public.fn_cancel_sale',
        EXISTS (SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
                 WHERE n.nspname = 'public' AND p.proname = 'fn_cancel_sale')),
    ('function public.fn_return_sale',
        EXISTS (SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
                 WHERE n.nspname = 'public' AND p.proname = 'fn_return_sale'))
)
SELECT objeto,
       CASE WHEN existe THEN 'ja existe' ELSE 'ainda nao' END AS situacao
  FROM depois;

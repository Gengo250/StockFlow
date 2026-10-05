-- 2026-10-05: aceita também banco novo vazio; mantém guards sobre dados reais.
-- Reconciliação do catálogo (categories/products) com o schema canônico.
--
-- ------------------------------------------------------------------ causa
--
-- O schema público do remoto foi construído/remendado à mão e não corresponde
-- a nenhuma versão das migrations do histórico:
--
--   * 20261001185718_tables_products.sql foi APLICADA em 2026-10-01 com a
--     versão cc904e5 (categories/products sem company_id, barcode UNIQUE
--     sozinho, FK simples item_category -> categories(id)). O commit d96cd7d
--     reescreveu aquele arquivo já aplicado para a versão multi-tenant; o
--     timestamp já estava em supabase_migrations.schema_migrations e o
--     conteúdo novo nunca rodou.
--   * 20261001185720_procedures_products.sql teve o mesmo destino: aplicada
--     como create_categories/create_products, reescrita depois (90cb6e4) para
--     fn_create_categories/fn_create_products, que nunca chegaram ao banco.
--   * Além disso, nenhuma migration do histórico contém um único ALTER TABLE,
--     mas o remoto tem company_id em categories/products e products.unit como
--     integer com CHECK (unit > 0). Essas mudanças foram feitas fora do
--     controle de migrations, direto no SQL Editor.
--
-- Resultado: products.unit é integer, não existe public.unit_enum, as colunas
-- company_id são nullable, faltam as constraints multi-tenant, sobraram as
-- funções legadas fn_create_category/fn_create_product e faltam as canônicas
-- fn_create_categories/fn_create_products — que 20261003120100 exige.
--
-- ----------------------------------------------------------------- escopo
--
-- Esta migration leva o banco legado ATÉ o schema canônico, nunca o
-- contrário. Fontes canônicas (verificadas idênticas entre as duas árvores):
--
--   database/code/tables/03_catalog.sql
--   database/code/procedures/05_catalog.sql
--   database/supabase/schemas/tables/03_catalog.sql
--   database/supabase/schemas/procedures/05_catalog.sql
--
-- As migrations já aplicadas não são tocadas. 20261003120100 e 20261003120200
-- não foram alteradas: o trabalho de preparar o schema para elas é todo aqui.
--
-- A migration é deliberadamente paranoica. O inventário de divergências do
-- remoto é sabidamente incompleto ("entre as divergências"), então cada
-- alteração é condicionada ao catálogo real e o bloco final reassere o
-- resultado. Qualquer divergência não prevista aborta a migration inteira
-- (o CLI roda cada migration em transação) em vez de deixar schema pela
-- metade.

-- =====================================================================
-- A. GUARDS — o estado precisa ser exatamente o diagnosticado
-- =====================================================================

DO $$
DECLARE
  v_products   bigint;
  v_company    bigint;
  v_categories bigint;
  v_sonda      bigint;
  v_faltando   text[];
BEGIN
  -- A.1 As tabelas precisam existir antes de qualquer coisa.
  IF to_regclass('public.company')    IS NULL THEN RAISE EXCEPTION 'public.company não existe';    END IF;
  IF to_regclass('public.categories') IS NULL THEN RAISE EXCEPTION 'public.categories não existe'; END IF;
  IF to_regclass('public.products')   IS NULL THEN RAISE EXCEPTION 'public.products não existe';   END IF;

  -- A.2 Todas as colunas canônicas precisam existir. Coluna faltando é
  -- divergência estrutural fora do escopo desta reconciliação: para aqui em
  -- vez de inventar ADD COLUMN não autorizado.
  SELECT array_agg(x.col ORDER BY x.col) INTO v_faltando
    FROM unnest(ARRAY['id','company_id','name']) AS x(col)
   WHERE NOT EXISTS (
     SELECT 1 FROM information_schema.columns c
      WHERE c.table_schema = 'public' AND c.table_name = 'categories'
        AND c.column_name = x.col);
  IF v_faltando IS NOT NULL THEN
    RAISE EXCEPTION 'public.categories sem colunas canônicas: %', array_to_string(v_faltando, ', ');
  END IF;

  SELECT array_agg(x.col ORDER BY x.col) INTO v_faltando
    FROM unnest(ARRAY['id','company_id','barcode','name','buy_price','sell_price',
                      'unit','stock','item_category','active','created_on']) AS x(col)
   WHERE NOT EXISTS (
     SELECT 1 FROM information_schema.columns c
      WHERE c.table_schema = 'public' AND c.table_name = 'products'
        AND c.column_name = x.col);
  IF v_faltando IS NOT NULL THEN
    RAISE EXCEPTION 'public.products sem colunas canônicas: %', array_to_string(v_faltando, ', ');
  END IF;

  -- A.3 Precondições de dados. Tudo o que vem depois (SET NOT NULL em
  -- company_id, troca do tipo de unit, UNIQUE multi-tenant, DELETE da
  -- categoria órfã) só é seguro porque as tabelas estão vazias.
  SELECT count(*) INTO v_products   FROM public.products;
  SELECT count(*) INTO v_company    FROM public.company;
  SELECT count(*) INTO v_categories FROM public.categories;
  SELECT count(*) INTO v_sonda      FROM public.categories
   WHERE name = '__sonda__' AND company_id IS NULL;

  IF v_products <> 0 THEN
    RAISE EXCEPTION 'Abortado: public.products tem % linha(s); esperado 0. '
                    'Com dados reais a conversão de unit e os NOT NULL exigem '
                    'backfill, que esta migration não faz.', v_products;
  END IF;

  IF v_company <> 0 THEN
    RAISE EXCEPTION 'Abortado: public.company tem % linha(s); esperado 0. '
                    'Com empresas reais a categoria órfã pode ter dono '
                    'legítimo e não pode ser apagada às cegas.', v_company;
  END IF;

  IF v_categories NOT IN (0, 1) THEN
    RAISE EXCEPTION 'Abortado: public.categories tem % linha(s); esperado '
                    '0 (banco novo) ou 1 (a sonda).', v_categories;
  END IF;

  IF v_categories = 1 AND v_sonda <> 1 THEN
    RAISE EXCEPTION 'Abortado: a única linha de public.categories não é a '
                    'sonda esperada (name = ''__sonda__'' AND company_id IS NULL).';
  END IF;
END $$;

-- =====================================================================
-- B. Resíduo de sondagem: a categoria órfã
-- =====================================================================
--
-- company está vazia, logo não existe company_id legítimo para adotar essa
-- linha. Não se cria empresa, não se usa UUID fixo, não se usa MIN(id): a
-- linha é resíduo de teste e sai. Os guards de A.3 já provaram que ela é a
-- única linha, que tem company_id NULL, que se chama exatamente '__sonda__' e
-- que nenhum produto a referencia (products está vazia).

DELETE FROM public.categories
 WHERE name = '__sonda__'
   AND company_id IS NULL;

-- =====================================================================
-- C. public.unit_enum
-- =====================================================================
--
-- Cria se não existir. Se existir, valida rótulos E ordem: a ordem do enum
-- define comparação e ORDER BY, então um enum com os mesmos rótulos em ordem
-- diferente é incompatível, não equivalente. Nada de aceitar em silêncio.

DO $$
DECLARE
  v_oid      oid;
  v_typtype  "char";
  v_labels   text[];
  v_esperado text[] := ARRAY['UN', 'PCT', 'DZ', 'G', 'KG', 'L', 'ML'];
BEGIN
  SELECT t.oid, t.typtype INTO v_oid, v_typtype
    FROM pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
   WHERE n.nspname = 'public' AND t.typname = 'unit_enum';

  IF v_oid IS NULL THEN
    CREATE TYPE public.unit_enum AS ENUM ('UN', 'PCT', 'DZ', 'G', 'KG', 'L', 'ML');
    RAISE NOTICE 'public.unit_enum criado.';
    RETURN;
  END IF;

  IF v_typtype <> 'e' THEN
    RAISE EXCEPTION 'public.unit_enum existe mas não é um ENUM (typtype = %).', v_typtype;
  END IF;

  SELECT array_agg(e.enumlabel::text ORDER BY e.enumsortorder) INTO v_labels
    FROM pg_enum e WHERE e.enumtypid = v_oid;

  IF v_labels IS DISTINCT FROM v_esperado THEN
    RAISE EXCEPTION 'public.unit_enum existe com rótulos/ordem incompatíveis. '
                    'Encontrado: [%]. Esperado: [%].',
                    array_to_string(v_labels, ', '), array_to_string(v_esperado, ', ');
  END IF;

  RAISE NOTICE 'public.unit_enum já existe e confere.';
END $$;

-- =====================================================================
-- D. products.unit: integer -> public.unit_enum
-- =====================================================================
--
-- O CHECK legado (unit > 0) é sobre um integer e precisa sair antes da troca
-- de tipo. products está vazia (guard A.3), então não há mapeamento
-- integer -> enum a inventar: o USING nunca é avaliado, porque não existe
-- linha para avaliar.
--
-- A única view do schema (vw_stock_situation) não projeta products.unit, logo
-- não bloqueia o ALTER TYPE.

ALTER TABLE public.products DROP CONSTRAINT IF EXISTS products_unit_check;

DO $$
DECLARE
  v_udt text;
BEGIN
  SELECT c.udt_name INTO v_udt
    FROM information_schema.columns c
   WHERE c.table_schema = 'public' AND c.table_name = 'products' AND c.column_name = 'unit';

  IF v_udt = 'unit_enum' THEN
    RAISE NOTICE 'products.unit já é public.unit_enum.';
    RETURN;
  END IF;

  -- DROP DEFAULT primeiro: o default legado é um literal do tipo antigo e não
  -- sobrevive ao ALTER TYPE.
  ALTER TABLE public.products ALTER COLUMN unit DROP DEFAULT;
  EXECUTE 'ALTER TABLE public.products ALTER COLUMN unit TYPE public.unit_enum '
          'USING NULL::public.unit_enum';
  RAISE NOTICE 'products.unit convertido de % para public.unit_enum.', v_udt;
END $$;

-- =====================================================================
-- E. Nullability e defaults
-- =====================================================================
--
-- Idempotente: SET NOT NULL / SET DEFAULT em coluna que já está assim é
-- no-op. Sem backfill porque as duas tabelas estão vazias (guard A.3 +
-- DELETE da seção B) — nenhum registro é inventado para satisfazer NOT NULL.

ALTER TABLE public.categories ALTER COLUMN company_id SET NOT NULL;

ALTER TABLE public.products   ALTER COLUMN company_id SET NOT NULL;
ALTER TABLE public.products   ALTER COLUMN unit       SET DEFAULT 'UN'::public.unit_enum;
ALTER TABLE public.products   ALTER COLUMN unit       SET NOT NULL;
ALTER TABLE public.products   ALTER COLUMN stock      SET DEFAULT 0;
ALTER TABLE public.products   ALTER COLUMN stock      SET NOT NULL;
ALTER TABLE public.products   ALTER COLUMN active     SET DEFAULT true;
ALTER TABLE public.products   ALTER COLUMN active     SET NOT NULL;
ALTER TABLE public.products   ALTER COLUMN created_on SET DEFAULT now();
ALTER TABLE public.products   ALTER COLUMN created_on SET NOT NULL;

-- =====================================================================
-- F. Constraints multi-tenant
-- =====================================================================
--
-- ADD CONSTRAINT não tem IF NOT EXISTS, então cada adição é condicionada ao
-- conjunto de colunas em pg_constraint.conkey — e não ao nome. Assim uma
-- constraint equivalente criada à mão sob outro nome não vira duplicata.

-- F.1 categories: UNIQUE (company_id, name)
DO $$
DECLARE v_rel oid := 'public.categories'::regclass;
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint c
     WHERE c.conrelid = v_rel AND c.contype = 'u'
       AND c.conkey = (SELECT array_agg(a.attnum ORDER BY x.ord)
                         FROM unnest(ARRAY['company_id','name']) WITH ORDINALITY AS x(col, ord)
                         JOIN pg_attribute a ON a.attrelid = v_rel AND a.attname = x.col)
  ) THEN
    ALTER TABLE public.categories
      ADD CONSTRAINT categories_company_id_name_key UNIQUE (company_id, name);
    RAISE NOTICE 'categories: UNIQUE (company_id, name) adicionada.';
  END IF;
END $$;

-- F.2 categories: UNIQUE (company_id, id) — alvo da FK composta de products.
DO $$
DECLARE v_rel oid := 'public.categories'::regclass;
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint c
     WHERE c.conrelid = v_rel AND c.contype = 'u'
       AND c.conkey = (SELECT array_agg(a.attnum ORDER BY x.ord)
                         FROM unnest(ARRAY['company_id','id']) WITH ORDINALITY AS x(col, ord)
                         JOIN pg_attribute a ON a.attrelid = v_rel AND a.attname = x.col)
  ) THEN
    ALTER TABLE public.categories
      ADD CONSTRAINT categories_company_id_id_key UNIQUE (company_id, id);
    RAISE NOTICE 'categories: UNIQUE (company_id, id) adicionada.';
  END IF;
END $$;

-- F.3 categories: CHECK (btrim(name) <> ''). Está no canônico e não aparece
-- no inventário do remoto.
DO $$
DECLARE v_rel oid := 'public.categories'::regclass;
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint c
     WHERE c.conrelid = v_rel AND c.contype = 'c'
       AND pg_get_constraintdef(c.oid) ILIKE '%btrim(name)%'
  ) THEN
    ALTER TABLE public.categories
      ADD CONSTRAINT categories_name_check CHECK (btrim(name) <> '');
    RAISE NOTICE 'categories: CHECK (btrim(name) <> '''') adicionada.';
  END IF;
END $$;

-- F.4 products: troca UNIQUE (barcode) por UNIQUE (company_id, barcode).
-- Código de barras é único dentro da empresa, não globalmente: com o UNIQUE
-- antigo, uma empresa cadastrando um EAN impediria todas as outras.
ALTER TABLE public.products DROP CONSTRAINT IF EXISTS products_barcode_key;

DO $$
DECLARE v_rel oid := 'public.products'::regclass;
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint c
     WHERE c.conrelid = v_rel AND c.contype = 'u'
       AND c.conkey = (SELECT array_agg(a.attnum ORDER BY x.ord)
                         FROM unnest(ARRAY['company_id','barcode']) WITH ORDINALITY AS x(col, ord)
                         JOIN pg_attribute a ON a.attrelid = v_rel AND a.attname = x.col)
  ) THEN
    ALTER TABLE public.products
      ADD CONSTRAINT products_company_id_barcode_key UNIQUE (company_id, barcode);
    RAISE NOTICE 'products: UNIQUE (company_id, barcode) adicionada.';
  END IF;
END $$;

-- F.5 products: CHECK (btrim(name) <> '').
DO $$
DECLARE v_rel oid := 'public.products'::regclass;
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint c
     WHERE c.conrelid = v_rel AND c.contype = 'c'
       AND pg_get_constraintdef(c.oid) ILIKE '%btrim(name)%'
  ) THEN
    ALTER TABLE public.products
      ADD CONSTRAINT products_name_check CHECK (btrim(name) <> '');
    RAISE NOTICE 'products: CHECK (btrim(name) <> '''') adicionada.';
  END IF;
END $$;

-- F.6 products: FK simples item_category -> FK composta (company_id, item_category).
-- A FK simples deixa um produto apontar para categoria de OUTRA empresa. A
-- composta amarra produto e categoria à mesma empresa no nível do banco, que
-- é o que o canônico pede. Depende do UNIQUE (company_id, id) criado em F.2.
ALTER TABLE public.products DROP CONSTRAINT IF EXISTS products_item_category_fkey;

DO $$
DECLARE
  v_rel oid := 'public.products'::regclass;
  v_ref oid := 'public.categories'::regclass;
BEGIN
  -- Qualquer FK remanescente sobre item_category sozinho é a versão antiga.
  IF EXISTS (
    SELECT 1 FROM pg_constraint c
     WHERE c.conrelid = v_rel AND c.contype = 'f'
       AND c.conkey = (SELECT ARRAY[a.attnum] FROM pg_attribute a
                        WHERE a.attrelid = v_rel AND a.attname = 'item_category')
  ) THEN
    RAISE EXCEPTION 'Ainda existe FK de products apenas sobre item_category, '
                    'sob nome diferente de products_item_category_fkey. '
                    'Remova-a antes de reaplicar.';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint c
     WHERE c.conrelid = v_rel AND c.contype = 'f' AND c.confrelid = v_ref
       AND c.conkey = (SELECT array_agg(a.attnum ORDER BY x.ord)
                         FROM unnest(ARRAY['company_id','item_category']) WITH ORDINALITY AS x(col, ord)
                         JOIN pg_attribute a ON a.attrelid = v_rel AND a.attname = x.col)
  ) THEN
    ALTER TABLE public.products
      ADD CONSTRAINT products_company_id_item_category_fkey
      FOREIGN KEY (company_id, item_category)
      REFERENCES public.categories (company_id, id)
      ON DELETE SET NULL (item_category);
    RAISE NOTICE 'products: FK composta (company_id, item_category) adicionada.';
  END IF;
END $$;

-- F.7 products.company_id -> company(id) precisa ser ON DELETE CASCADE, como
-- em categories e como no canônico. O remoto tem a FK sem ação de delete, o
-- que faria DELETE de empresa falhar em vez de limpar o catálogo dela.
-- A FK é preservada: só a ação de delete é reconciliada.
DO $$
DECLARE
  v_rel  oid := 'public.products'::regclass;
  v_nome text;
  v_del  "char";
BEGIN
  SELECT c.conname, c.confdeltype INTO v_nome, v_del
    FROM pg_constraint c
   WHERE c.conrelid = v_rel AND c.contype = 'f'
     AND c.confrelid = 'public.company'::regclass
     AND c.conkey = (SELECT ARRAY[a.attnum] FROM pg_attribute a
                      WHERE a.attrelid = v_rel AND a.attname = 'company_id');

  IF v_nome IS NULL THEN
    RAISE EXCEPTION 'products não tem FK company_id -> company(id).';
  END IF;

  IF v_del <> 'c' THEN
    EXECUTE format('ALTER TABLE public.products DROP CONSTRAINT %I', v_nome);
    ALTER TABLE public.products
      ADD CONSTRAINT products_company_id_fkey
      FOREIGN KEY (company_id) REFERENCES public.company(id) ON DELETE CASCADE;
    RAISE NOTICE 'products: FK company_id recriada com ON DELETE CASCADE.';
  END IF;
END $$;

-- F.8 Índice de apoio do canônico. Condicionado às colunas indexadas, não ao
-- nome: IF NOT EXISTS casa só por nome e aceitaria em silêncio um índice
-- homônimo sobre outras colunas.
DO $$
DECLARE v_rel oid := 'public.products'::regclass;
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_index i
     WHERE i.indrelid = v_rel
       AND i.indnkeyatts = 1
       AND i.indkey[0] = (SELECT a.attnum FROM pg_attribute a
                           WHERE a.attrelid = v_rel AND a.attname = 'company_id')
  ) THEN
    CREATE INDEX idx_products_company ON public.products (company_id);
    RAISE NOTICE 'products: idx_products_company criado.';
  END IF;
END $$;

-- =====================================================================
-- G. Funções legadas
-- =====================================================================
--
-- fn_create_category/fn_create_product vêm de
-- database/archive/functions/product/create_product.sql (commit 896807b,
-- branch companies_user_stock_configure) — arquivo que não existe mais na
-- árvore e que nunca virou migration. Foram substituídas por
-- fn_create_categories/fn_create_products, que são a API usada pelo código e
-- a exigida por 20261003120100.
--
-- A remoção não é cosmética: fn_create_product recebe p_unit INTEGER e insere
-- direto em products.unit. Depois da seção D essa coluna é unit_enum, então a
-- função legada está quebrada de qualquer forma.
--
-- Assinaturas exatas, nada de DROP amplo. Nenhuma referência a esses nomes em
-- database/, src/, tests/ ou scripts/.

DROP FUNCTION IF EXISTS public.fn_create_category(uuid, text);
DROP FUNCTION IF EXISTS public.fn_create_product(uuid, text, text, numeric, integer, numeric, integer, uuid);

-- =====================================================================
-- H. Funções canônicas
-- =====================================================================
--
-- Cópia literal de database/code/procedures/05_catalog.sql (idêntico a
-- database/supabase/schemas/procedures/05_catalog.sql). Assinaturas,
-- SECURITY DEFINER, search_path, fn_has_role com ADMIN/STOCK, escopo por
-- company_id, tratamento de categoria, defaults e retorno UUID preservados
-- sem simplificação.
--
-- Sem GRANT aqui: quem reabre EXECUTE para app_backend é
-- 20261003120100_policies_security.sql, que roda em seguida e já lista as
-- duas em v_names.

CREATE OR REPLACE FUNCTION public.fn_create_categories (
  p_company_id UUID,
  p_name       TEXT
)
RETURNS UUID
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
  v_new_id UUID;
BEGIN
  IF NOT public.fn_has_role(p_company_id, ARRAY['ADMIN','STOCK']::public.user_role[]) THEN
    RAISE EXCEPTION 'Sem permissão para cadastrar categorias nesta empresa'
      USING ERRCODE = 'insufficient_privilege';
  END IF;

  -- categories é UNIQUE (company_id, name): o mesmo nome pode existir em
  -- outra empresa, então a checagem precisa ser escopada.
  IF EXISTS (
    SELECT 1 FROM public.categories
     WHERE company_id = p_company_id AND name = p_name
  ) THEN
    RAISE EXCEPTION 'Category already exists' USING ERRCODE = 'unique_violation';
  END IF;

  INSERT INTO public.categories (
    company_id,
    name
  )
  VALUES (
    p_company_id,
    p_name
  )
  RETURNING id INTO v_new_id;

  RETURN v_new_id;
END;
$$;

CREATE OR REPLACE FUNCTION public.fn_create_products (
  p_company_id    UUID,
  p_barcode       TEXT,
  p_name          TEXT,
  p_sell_price    NUMERIC (10, 2),
  p_buy_price     NUMERIC (10, 2)   DEFAULT NULL,
  p_unit          public.unit_enum  DEFAULT 'UN',
  p_stock         INTEGER           DEFAULT 0,
  p_item_category TEXT              DEFAULT NULL
)
RETURNS UUID
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
  v_new_id      UUID;
  v_category_id UUID;
BEGIN
  IF NOT public.fn_has_role(p_company_id, ARRAY['ADMIN','STOCK']::public.user_role[]) THEN
    RAISE EXCEPTION 'Sem permissão para cadastrar produtos nesta empresa'
      USING ERRCODE = 'insufficient_privilege';
  END IF;

  IF p_item_category IS NOT NULL THEN
    SELECT id INTO v_category_id
      FROM public.categories
     WHERE company_id = p_company_id AND name = p_item_category;

    IF v_category_id IS NULL THEN
      RAISE EXCEPTION 'Item category doesnt exist' USING ERRCODE = 'foreign_key_violation';

    END IF;
  END IF;

  INSERT INTO public.products (
    company_id,
    barcode,
    name,
    buy_price,
    sell_price,
    unit,
    stock,
    item_category
  )
  VALUES (
    p_company_id,
    p_barcode,
    p_name,
    p_buy_price,
    p_sell_price,
    p_unit,
    p_stock,
    v_category_id
  )
  RETURNING id into v_new_id;

  RETURN v_new_id;
END;
$$;

-- =====================================================================
-- I. Asserção final
-- =====================================================================
--
-- O inventário de divergências do remoto é incompleto por construção, então o
-- resultado é reconferido aqui. Acumula tudo o que estiver errado e levanta
-- uma exceção só no fim, para o erro mostrar a lista inteira em vez de uma
-- falha por vez. Mesmo padrão de 20261003120100.

DO $$
DECLARE
  v_rel   oid := 'public.products'::regclass;
  v_cat   oid := 'public.categories'::regclass;
  v_erros text[] := '{}';
  v_txt   text;
  v_bool  boolean;
BEGIN
  -- I.1 unit_enum
  SELECT array_to_string(array_agg(e.enumlabel::text ORDER BY e.enumsortorder), ',') INTO v_txt
    FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid
    JOIN pg_namespace n ON n.oid = t.typnamespace
   WHERE n.nspname = 'public' AND t.typname = 'unit_enum';
  IF v_txt IS DISTINCT FROM 'UN,PCT,DZ,G,KG,L,ML' THEN
    v_erros := v_erros || format('unit_enum = [%s]', COALESCE(v_txt, '<ausente>'));
  END IF;

  -- I.2 products.unit. O default é comparado por padrão, não por igualdade:
  -- information_schema renderiza o cast com ou sem o prefixo "public."
  -- conforme o search_path da sessão, e as duas formas são corretas.
  SELECT format('%s/%s/%s', c.udt_name, c.is_nullable, COALESCE(c.column_default, '<sem default>'))
    INTO v_txt
    FROM information_schema.columns c
   WHERE c.table_schema='public' AND c.table_name='products' AND c.column_name='unit';
  IF v_txt NOT LIKE 'unit_enum/NO/''UN''::%unit_enum' THEN
    v_erros := v_erros || format(
      'products.unit = %s (esperado unit_enum/NO/''UN''::unit_enum)', v_txt);
  END IF;

  -- I.3 NOT NULL e defaults
  FOR v_txt IN
    SELECT format('%s.%s', t.tab, t.col)
      FROM (VALUES ('categories','company_id'), ('products','company_id'),
                   ('products','stock'), ('products','active'), ('products','created_on')
           ) AS t(tab, col)
      JOIN information_schema.columns c
        ON c.table_schema='public' AND c.table_name=t.tab AND c.column_name=t.col
     WHERE c.is_nullable <> 'NO'
  LOOP
    v_erros := v_erros || format('%s ainda é nullable', v_txt);
  END LOOP;

  SELECT c.column_default IS NOT DISTINCT FROM '0' INTO v_bool
    FROM information_schema.columns c
   WHERE c.table_schema='public' AND c.table_name='products' AND c.column_name='stock';
  IF NOT COALESCE(v_bool, false) THEN
    v_erros := v_erros || 'products.stock sem DEFAULT 0';
  END IF;

  -- I.4 UNIQUE multi-tenant
  IF NOT EXISTS (SELECT 1 FROM pg_constraint c WHERE c.conrelid=v_cat AND c.contype='u'
      AND c.conkey = (SELECT array_agg(a.attnum ORDER BY x.ord)
                        FROM unnest(ARRAY['company_id','name']) WITH ORDINALITY AS x(col,ord)
                        JOIN pg_attribute a ON a.attrelid=v_cat AND a.attname=x.col)) THEN
    v_erros := v_erros || 'categories sem UNIQUE (company_id, name)';
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_constraint c WHERE c.conrelid=v_cat AND c.contype='u'
      AND c.conkey = (SELECT array_agg(a.attnum ORDER BY x.ord)
                        FROM unnest(ARRAY['company_id','id']) WITH ORDINALITY AS x(col,ord)
                        JOIN pg_attribute a ON a.attrelid=v_cat AND a.attname=x.col)) THEN
    v_erros := v_erros || 'categories sem UNIQUE (company_id, id)';
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_constraint c WHERE c.conrelid=v_rel AND c.contype='u'
      AND c.conkey = (SELECT array_agg(a.attnum ORDER BY x.ord)
                        FROM unnest(ARRAY['company_id','barcode']) WITH ORDINALITY AS x(col,ord)
                        JOIN pg_attribute a ON a.attrelid=v_rel AND a.attname=x.col)) THEN
    v_erros := v_erros || 'products sem UNIQUE (company_id, barcode)';
  END IF;

  -- I.5 Nada de UNIQUE global em barcode
  IF EXISTS (SELECT 1 FROM pg_constraint c WHERE c.conrelid=v_rel AND c.contype='u'
      AND c.conkey = (SELECT ARRAY[a.attnum] FROM pg_attribute a
                       WHERE a.attrelid=v_rel AND a.attname='barcode')) THEN
    v_erros := v_erros || 'products ainda tem UNIQUE (barcode) global';
  END IF;

  -- I.6 FK composta de categoria, com ON DELETE SET NULL
  IF NOT EXISTS (SELECT 1 FROM pg_constraint c
      WHERE c.conrelid=v_rel AND c.contype='f' AND c.confrelid=v_cat AND c.confdeltype='n'
        AND c.conkey = (SELECT array_agg(a.attnum ORDER BY x.ord)
                          FROM unnest(ARRAY['company_id','item_category']) WITH ORDINALITY AS x(col,ord)
                          JOIN pg_attribute a ON a.attrelid=v_rel AND a.attname=x.col)) THEN
    v_erros := v_erros || 'products sem FK (company_id, item_category) -> categories (company_id, id) ON DELETE SET NULL';
  END IF;

  IF EXISTS (SELECT 1 FROM pg_constraint c WHERE c.conrelid=v_rel AND c.contype='f'
      AND c.conkey = (SELECT ARRAY[a.attnum] FROM pg_attribute a
                       WHERE a.attrelid=v_rel AND a.attname='item_category')) THEN
    v_erros := v_erros || 'products ainda tem FK simples sobre item_category';
  END IF;

  -- I.7 Checks de preço e estoque preservados. O padrão para no ">=" de
  -- propósito: em coluna numeric o catálogo renderiza o literal como
  -- "(0)::numeric", em integer como "0".
  FOREACH v_txt IN ARRAY ARRAY['buy_price','sell_price','stock'] LOOP
    IF NOT EXISTS (SELECT 1 FROM pg_constraint c
        WHERE c.conrelid=v_rel AND c.contype='c'
          AND pg_get_constraintdef(c.oid) LIKE '%' || v_txt || ' >= %') THEN
      v_erros := v_erros || format('products perdeu o CHECK (%s >= 0)', v_txt);
    END IF;
  END LOOP;

  -- I.8 Funções canônicas presentes e SECURITY DEFINER
  FOREACH v_txt IN ARRAY ARRAY[
    'public.fn_create_categories(uuid,text)',
    'public.fn_create_products(uuid,text,text,numeric,numeric,public.unit_enum,integer,text)'
  ] LOOP
    -- to_regprocedure e não o cast ::regprocedure: o cast levanta
    -- undefined_function quando a assinatura não existe, e aqui o que se quer
    -- é registrar a ausência junto com os outros erros.
    SELECT p.prosecdef INTO v_bool
      FROM pg_proc p WHERE p.oid = to_regprocedure(v_txt);
    IF v_bool IS NULL THEN
      v_erros := v_erros || format('%s não existe', v_txt);
    ELSIF NOT v_bool THEN
      v_erros := v_erros || format('%s não é SECURITY DEFINER', v_txt);
    END IF;
  END LOOP;

  -- I.9 Funções legadas removidas
  IF EXISTS (SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
              WHERE n.nspname='public' AND p.proname IN ('fn_create_category','fn_create_product')) THEN
    v_erros := v_erros || 'fn_create_category/fn_create_product ainda existem';
  END IF;

  IF array_length(v_erros, 1) > 0 THEN
    RAISE EXCEPTION 'Reconciliação do catálogo incompleta: %', array_to_string(v_erros, '; ');
  END IF;

  RAISE NOTICE 'Catálogo reconciliado com o schema canônico.';
END $$;

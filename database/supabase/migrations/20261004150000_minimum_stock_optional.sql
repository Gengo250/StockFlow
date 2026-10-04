-- Estoque mínimo passa a ser OPCIONAL: ausente e zero deixam de ser a mesma coisa.
--
-- POR QUE
--
-- `product_stock.min_quantity` era `NOT NULL DEFAULT 0`. Com isso o número
-- zero carregava dois significados incompatíveis: "ninguém configurou mínimo
-- para este produto" e "o mínimo deste produto é zero, avise quando acabar".
-- A US03 pede que os dois sejam distinguíveis, e eles não são distinguíveis
-- dentro de um inteiro não nulo — falta um terceiro valor, e esse valor é NULL.
--
-- Depois desta migration:
--   mínimo NULL -> nunca alerta, em nenhum saldo;
--   mínimo 0    -> alerta quando o saldo chega a zero;
--   mínimo N>0  -> alerta quando o saldo chega a N.
--
-- POR QUE O DROP DEFAULT É TÃO OBRIGATÓRIO QUANTO O DROP NOT NULL
--
-- O gatilho `trg_products_create_stock` grava a linha de estoque de todo
-- produto novo sem citar `min_quantity`. Enquanto houvesse `DEFAULT 0`, cada
-- produto cadastrado nasceria com mínimo ZERO EXPLÍCITO — que agora alerta —
-- e a caixa de entrada de alertas encheria de produto que ninguém configurou.
-- Tirar só o NOT NULL resolveria o tipo e manteria o bug.
--
-- POR QUE O BACKFILL 0 -> NULL
--
-- Toda linha que hoje tem zero foi gravada quando zero significava
-- "não configurado": ou veio do default do gatilho, ou de uma tela que não
-- oferecia a opção de deixar em branco. Preservá-las como zero explícito
-- transformaria o dia da migration em uma enxurrada de alertas retroativos
-- que nenhum usuário pediu. Aprovado explicitamente antes de escrever isto.

-- ============================================================== 1. a coluna

ALTER TABLE public.product_stock ALTER COLUMN min_quantity DROP NOT NULL;
ALTER TABLE public.product_stock ALTER COLUMN min_quantity DROP DEFAULT;

UPDATE public.product_stock SET min_quantity = NULL WHERE min_quantity = 0;

-- ========================================================= 2. a classificação
--
-- A ORDEM das cláusulas é a regra, não um detalhe de escrita: o teste de NULL
-- vem antes do teste de saldo porque mínimo ausente não alerta nem com saldo
-- negativo, e o teste de saldo vem antes do de mínimo zero porque zerar é
-- exatamente o que o mínimo zero quer avisar.
--
-- A terceira cláusula não é redundante com o ELSE: com `p_min = 0`,
-- `p_min * 1.2` também é zero, então saldo 5 com mínimo 0 não casa com
-- nenhuma das comparações seguintes e cairia no ELSE por acidente — um dia
-- alguém mexeria no ELSE sem perceber que ele carregava esse caso.

CREATE OR REPLACE FUNCTION public.fn_stock_state(
    p_stock integer,
    p_min   integer
) RETURNS public.stock_state
LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE
        WHEN p_min IS NULL             THEN 'NORMAL'::public.stock_state
        WHEN COALESCE(p_stock, 0) <= 0 THEN 'CRITICO'::public.stock_state
        WHEN p_min = 0                 THEN 'NORMAL'::public.stock_state
        WHEN p_stock <= p_min          THEN 'BAIXO'::public.stock_state
        WHEN p_stock <  p_min * 1.2    THEN 'ATENCAO'::public.stock_state
        ELSE                                'NORMAL'::public.stock_state
    END;
$$;

-- ============================================================= 3. a escrita
--
-- Some a exigência de `p_min` não nulo. NULL vira o modo legítimo de LIMPAR o
-- mínimo: sem ele não haveria como desfazer uma configuração, só zerá-la — e
-- zero agora alerta, então "desfazer" viraria "ligar o alerta no fim do
-- estoque", o oposto da intenção. A rejeição de negativo continua e continua
-- correta com NULL: `NULL < 0` é NULL, o IF não dispara.

CREATE OR REPLACE FUNCTION public.fn_set_min_stock(
    p_product_id uuid,
    p_min        integer
) RETURNS void
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_company uuid;
BEGIN
    IF p_min < 0 THEN
        RAISE EXCEPTION 'Estoque mínimo não pode ser negativo (recebido: %)', p_min
            USING ERRCODE = 'check_violation';
    END IF;

    SELECT company_id INTO v_company FROM public.products WHERE id = p_product_id;

    IF v_company IS NULL
       OR NOT public.fn_has_role(v_company, ARRAY['ADMIN','STOCK']::public.user_role[]) THEN
        RAISE EXCEPTION 'Produto não encontrado ou sem permissão' USING ERRCODE = 'insufficient_privilege';
    END IF;

    INSERT INTO public.product_stock (product_id, min_quantity)
    VALUES (p_product_id, p_min)
    ON CONFLICT (product_id)
    DO UPDATE SET min_quantity = EXCLUDED.min_quantity;
END;
$$;

-- ============================================================== 4. as visões
--
-- Os dois COALESCE saem: o NULL é informação, não ausência a preencher.
-- Trocá-lo por zero apagaria a distinção antes mesmo de a classificação
-- poder decidir, e desfaria tudo que esta migration faz.

CREATE OR REPLACE VIEW public.vw_stock_situation
WITH (security_invoker = true) AS
SELECT
    p.company_id,
    p.id                                   AS product_id,
    p.name                                 AS product_name,
    p.stock                                AS current_balance,
    ps.min_quantity                        AS min_quantity,
    public.fn_stock_state(p.stock, ps.min_quantity) AS state
FROM public.products p
LEFT JOIN public.product_stock ps ON ps.product_id = p.id
WHERE p.active;

-- O filtro de alerta era `min_quantity > 0` e passava por "configurado".
-- Agora `> 0` silenciaria justamente quem configurou zero de propósito; quem
-- não configurou nada tem NULL e continua de fora pelo IS NOT NULL.

CREATE OR REPLACE VIEW public.vw_stock_alerts
WITH (security_invoker = true) AS
SELECT
    s.company_id,
    s.product_id,
    s.product_name,
    s.current_balance,
    s.min_quantity,
    s.state
FROM public.vw_stock_situation s
WHERE s.min_quantity IS NOT NULL
  AND s.current_balance <= s.min_quantity;

-- ========================================================== 5. as permissões
--
-- Reafirmadas de propósito. Substituir uma função preserva o ACL dela, mas um
-- ACL que por qualquer motivo tenha voltado a ser o padrão do Postgres é
-- aberto a PUBLIC — e descobrir isso em runtime custa caro. O fechamento é
-- barato e idempotente; a conferência do passo 6 é quem realmente garante.

REVOKE EXECUTE ON FUNCTION public.fn_stock_state(integer, integer) FROM PUBLIC, anon;
REVOKE EXECUTE ON FUNCTION public.fn_set_min_stock(uuid, integer) FROM PUBLIC, anon;
GRANT  EXECUTE ON FUNCTION public.fn_stock_state(integer, integer) TO app_backend, authenticated;
GRANT  EXECUTE ON FUNCTION public.fn_set_min_stock(uuid, integer) TO app_backend, authenticated;

-- ======================================================= 6. conferência obrigatória
--
-- Esta migration não pode se declarar bem-sucedida sem provar as três
-- afirmações que ela faz. Falhar aqui deixa o banco na transação anterior;
-- passar silenciosamente deixaria um banco que parece certo e alerta errado.

DO $$
DECLARE
  v_zeros     bigint;
  v_not_null  boolean;
  v_default   text;
  v_abertas   text;
BEGIN
  -- (a) O backfill foi completo. Qualquer zero sobrando é um zero herdado do
  -- significado antigo, e ele alertaria sem que ninguém tivesse pedido.
  SELECT count(*) INTO v_zeros FROM public.product_stock WHERE min_quantity = 0;

  IF v_zeros > 0 THEN
    RAISE EXCEPTION 'Restaram % linha(s) com mínimo zero herdado do significado antigo', v_zeros;
  END IF;

  -- (b) A coluna aceita NULL e não repõe zero sozinha. Sem as duas, o gatilho
  -- de criação de estoque volta a ligar alerta em todo produto novo.
  SELECT a.attnotnull, pg_get_expr(d.adbin, d.adrelid)
    INTO v_not_null, v_default
    FROM pg_attribute a
    LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
   WHERE a.attrelid = 'public.product_stock'::regclass
     AND a.attname = 'min_quantity';

  IF v_not_null THEN
    RAISE EXCEPTION 'product_stock.min_quantity continua NOT NULL: mínimo ausente seria impossível';
  END IF;

  IF v_default IS NOT NULL THEN
    RAISE EXCEPTION 'product_stock.min_quantity ainda tem default (%): todo produto novo nasceria alertando', v_default;
  END IF;

  -- (c) Nenhuma função ficou executável por PUBLIC/anon.
  SELECT string_agg(DISTINCT p.proname, ', ') INTO v_abertas
    FROM pg_proc p
    CROSS JOIN LATERAL aclexplode(COALESCE(p.proacl, acldefault('f', p.proowner))) acl
   WHERE p.pronamespace = 'public'::regnamespace
     AND p.prokind = 'f'
     AND acl.privilege_type = 'EXECUTE'
     AND (acl.grantee = 0 OR pg_get_userbyid(acl.grantee) = 'anon');

  IF v_abertas IS NOT NULL THEN
    RAISE EXCEPTION 'Ainda executáveis por PUBLIC/anon: %', v_abertas;
  END IF;
END $$;

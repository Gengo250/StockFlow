-- Clientes e vendas. Depende de company (01_identity) e products (03_catalog).

CREATE OR REPLACE FUNCTION public.fn_valid_br_document(p_document text)
RETURNS boolean
LANGUAGE plpgsql IMMUTABLE STRICT
SET search_path = public AS $$
DECLARE
    v_digits text := p_document;
    v_sum integer;
    v_remainder integer;
    v_first integer;
    v_second integer;
    i integer;
    v_weight integer;
BEGIN
    IF v_digits !~ '^[0-9]+$' OR v_digits IN (
        '00000000000', '11111111111', '22222222222', '33333333333',
        '44444444444', '55555555555', '66666666666', '77777777777',
        '88888888888', '99999999999',
        '00000000000000', '11111111111111', '22222222222222',
        '33333333333333', '44444444444444', '55555555555555',
        '66666666666666', '77777777777777', '88888888888888',
        '99999999999999'
    ) THEN
        RETURN false;
    END IF;

    IF length(v_digits) = 11 THEN
        v_sum := 0;
        FOR i IN 1..9 LOOP
            v_sum := v_sum + substring(v_digits, i, 1)::integer * (11 - i);
        END LOOP;
        v_remainder := v_sum % 11;
        v_first := CASE WHEN v_remainder < 2 THEN 0 ELSE 11 - v_remainder END;

        v_sum := 0;
        FOR i IN 1..10 LOOP
            v_weight := CASE WHEN i = 10 THEN 2 ELSE 12 - i END;
            v_sum := v_sum + substring(v_digits, i, 1)::integer * v_weight;
        END LOOP;
        v_remainder := v_sum % 11;
        v_second := CASE WHEN v_remainder < 2 THEN 0 ELSE 11 - v_remainder END;
        RETURN substring(v_digits, 10, 2) = (v_first::text || v_second::text);
    ELSIF length(v_digits) = 14 THEN
        v_sum := 0;
        FOR i IN 1..12 LOOP
            v_weight := CASE WHEN i <= 4 THEN 6 - i ELSE 14 - i END;
            v_sum := v_sum + substring(v_digits, i, 1)::integer * v_weight;
        END LOOP;
        v_remainder := v_sum % 11;
        v_first := CASE WHEN v_remainder < 2 THEN 0 ELSE 11 - v_remainder END;

        v_sum := 0;
        FOR i IN 1..13 LOOP
            v_weight := CASE WHEN i <= 5 THEN 7 - i ELSE 15 - i END;
            v_sum := v_sum + substring(v_digits, i, 1)::integer * v_weight;
        END LOOP;
        v_remainder := v_sum % 11;
        v_second := CASE WHEN v_remainder < 2 THEN 0 ELSE 11 - v_remainder END;
        RETURN substring(v_digits, 13, 2) = (v_first::text || v_second::text);
    END IF;

    RETURN false;
END;
$$;

CREATE TABLE public.clients (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id   uuid NOT NULL REFERENCES public.company(id) ON DELETE CASCADE,
    name         text NOT NULL CHECK (btrim(name) <> ''),
    document     text,
    email        text NOT NULL DEFAULT ''
                 CHECK (email = '' OR email ~ '^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$'),
    phone        text NOT NULL DEFAULT ''
                 CHECK (phone = '' OR (
                        phone ~ '^[+0-9().[:space:]-]+$' AND
                        length(regexp_replace(phone, '\D', '', 'g')) IN (10, 11))),
    notes        text NOT NULL DEFAULT '',
    active       boolean NOT NULL DEFAULT true,
    -- Autor do cadastro (H14), por fn_current_user_id(). Mesma ausência de FK
    -- de sales.created_by, logo abaixo.
    created_by   uuid,
    created_on   timestamptz NOT NULL DEFAULT now(),
    updated_on   timestamptz NOT NULL DEFAULT now(),
    CHECK (document IS NULL OR
           (document <> '' AND public.fn_valid_br_document(document))),
    UNIQUE (company_id, id)
);

-- Documentos são armazenados apenas com dígitos pela aplicação; NULL/'' não
-- participam da unicidade, mas documentos iguais não podem ser duplicados
-- nem por chamadas concorrentes.
CREATE UNIQUE INDEX uq_clients_company_document
    ON public.clients (company_id, document)
    WHERE document IS NOT NULL AND document <> '';
CREATE INDEX idx_clients_company_name
    ON public.clients (company_id, lower(name));

-- ------------------------------------------------------------------ vendas
--
-- Venda é CABEÇALHO + ITENS desde a US10: uma venda pode levar vários
-- produtos, e o preço/nome/código de cada item é congelado na linha do item.
-- Antes disso `sales` carregava um único produto em colunas próprias, o que
-- obrigava a abrir uma venda por produto e perdia o vínculo entre os itens da
-- mesma compra.
--
-- O snapshot continua sendo regra: `client_name` no cabeçalho e
-- `product_name`/`product_code` no item sobrevivem à renomeação do cliente e
-- à exclusão do produto. É por isso que a FK de produto é ON DELETE SET NULL
-- enquanto a de cliente é RESTRICT — cliente com venda não some; produto sim,
-- e a venda guarda o que foi vendido.

-- `DEVOLVIDA` entra na US17, junto com o cancelamento de venda. Os dois
-- estados são TERMINAIS e chegam por portas diferentes: cancelar anula as
-- saídas da venda; devolver grava entradas compensatórias e deixa a saída
-- original de pé. Quem distingue um do outro no registro é `sale_reversals`,
-- no fim deste arquivo.
CREATE TYPE public.sale_status AS ENUM (
    'PENDENTE', 'CONCLUIDA', 'CANCELADA', 'DEVOLVIDA'
);

-- Cancelar e devolver não são a mesma operação, e a diferença precisa
-- sobreviver no registro: cancelamento diz que a venda não deveria ter
-- existido; devolução diz que existiu e a mercadoria voltou.
CREATE TYPE public.sale_reversal_kind AS ENUM ('CANCELAMENTO', 'DEVOLUCAO');

-- Segue a nomenclatura de movement_kind/movement_status: rótulo em português
-- no banco, como o resto do domínio desta árvore.
CREATE TYPE public.payment_method AS ENUM (
    'DINHEIRO', 'DEBITO', 'CREDITO', 'PIX', 'VALE', 'OUTRO'
);

CREATE TABLE public.sales (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id       uuid NOT NULL REFERENCES public.company(id) ON DELETE CASCADE,
    -- Aceita nulo porque o schema implantado aceita. A aplicação é mais
    -- estrita que o banco aqui: `SaleService` recusa venda sem cliente ativo
    -- antes de gravar. Apertar a coluna exige antes conferir se há linha
    -- antiga com nulo, e isso é decisão com checagem de dado, não ajuste de
    -- arquivo.
    client_id        uuid,
    client_name      text NOT NULL,
    -- Herança do período em que `sales` foi recriada com outro desenho
    -- (migration 20261010231302). Nenhum caminho da aplicação lê ou grava
    -- esta coluna; está declarada porque existe no banco, e sair dela é
    -- remoção de coluna, que pede decisão própria.
    customer_document text,
    payment_method   public.payment_method NOT NULL DEFAULT 'DINHEIRO',
    -- Desconto do cabeçalho, já abatido em `total`. Guardado à parte porque a
    -- soma dos subtotais dos itens menos o desconto é o que reconcilia o
    -- total; sem a coluna não há como auditar a diferença.
    discount         numeric(10,2) NOT NULL DEFAULT 0 CHECK (discount >= 0),
    total            numeric(10,2) NOT NULL CHECK (total >= 0),
    original_total   numeric(10,2) GENERATED ALWAYS AS (total + discount) STORED,
    sale_discount_type text NOT NULL DEFAULT 'FIXED'
                       CHECK (sale_discount_type IN ('FIXED', 'PERCENTAGE')),
    sale_discount_value numeric(10,2) NOT NULL DEFAULT 0
                       CHECK (sale_discount_value >= 0 AND
                              (sale_discount_type <> 'PERCENTAGE'
                               OR sale_discount_value <= 100)),
    discount_applied_by uuid,
    discount_authorized_by uuid,
    -- Nasce PENDENTE: montar o carrinho não é fechar a venda. A baixa de
    -- estoque acontece na transição para CONCLUIDA (triggers/06).
    status           public.sale_status NOT NULL DEFAULT 'PENDENTE',
    -- Autor da venda (H14), por fn_current_user_id(). Sem chave estrangeira,
    -- como clients.created_by: a autoria precisa sobreviver à remoção da
    -- conta. Obrigatória, como no banco implantado — toda venda tem autor, e
    -- auditoria que aceita nulo não é auditoria.
    created_by       uuid NOT NULL,
    created_on       timestamptz NOT NULL DEFAULT now(),
    -- RESTRICT, e isso é decisão de domínio, não detalhe: cliente com venda
    -- no histórico não pode ser apagado. `tests/test_clientes_database_contract.py`
    -- cobra esta ação por nome. O banco implantado ficou com SET NULL desde a
    -- recriação da tabela em 20261010231302; quem corrige isso é a migration
    -- 20261101120000, não um afrouxamento aqui.
    FOREIGN KEY (company_id, client_id)
        REFERENCES public.clients (company_id, id) ON DELETE RESTRICT,
    -- Alvo da FK composta de sale_items, que garante que item e venda
    -- pertencem à mesma empresa.
    UNIQUE (company_id, id)
);
CREATE INDEX idx_sales_company_created
    ON public.sales (company_id, created_on DESC);

CREATE TABLE public.sale_discount_limits (
    company_id uuid NOT NULL REFERENCES public.company(id) ON DELETE CASCADE,
    role       public.user_role NOT NULL,
    limit_percent numeric(5,2)
                 CHECK (limit_percent IS NULL OR
                        limit_percent BETWEEN 0 AND 100),
    updated_by uuid,
    updated_on timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (company_id, role),
    CHECK (role = 'SELLER')
);

CREATE TABLE public.sale_items (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Redundante com sales.company_id, e proposital: a policy de RLS escopa
    -- por esta coluna sem entrar em `sales` a cada linha, como já acontece em
    -- stock_movements.
    company_id    uuid NOT NULL,
    sale_id       uuid NOT NULL,
    product_id    uuid,
    product_name  text NOT NULL,
    product_code  text NOT NULL,
    -- integer, como stock_movements.quantity: o item vira movimentação de
    -- saída na conclusão da venda, e quantidade fracionária ali seria
    -- truncada silenciosamente.
    quantity      integer NOT NULL CHECK (quantity > 0),
    unit_price    numeric(10,2) NOT NULL CHECK (unit_price >= 0),
    subtotal      numeric(10,2) NOT NULL
                  GENERATED ALWAYS AS (quantity * unit_price) STORED,
    discount_type text NOT NULL DEFAULT 'FIXED'
                  CHECK (discount_type IN ('FIXED', 'PERCENTAGE')),
    discount_value numeric(10,2) NOT NULL DEFAULT 0
                   CHECK (discount_value >= 0 AND
                          (discount_type <> 'PERCENTAGE'
                           OR discount_value <= 100)),
    discount_amount numeric(10,2) NOT NULL DEFAULT 0
                    CHECK (discount_amount >= 0 AND
                           discount_amount <= quantity * unit_price),
    -- Usar colunas-base; subtotal também é gerada. Mesma definição da migration.
    final_subtotal numeric(10,2)
                   GENERATED ALWAYS AS (quantity * unit_price - discount_amount) STORED,
    created_on    timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (company_id, sale_id)
        REFERENCES public.sales (company_id, id) ON DELETE CASCADE,
    FOREIGN KEY (product_id)
        REFERENCES public.products (id) ON DELETE SET NULL,
    -- Alvo da FK composta de return_items, pelo mesmo motivo do UNIQUE em
    -- `sales`: a devolução precisa apontar para um item da MESMA empresa e da
    -- MESMA venda. Sem esta linha o declarativo não aplicava — a chave
    -- estrangeira de `11_return_items.sql` não tinha alvo único.
    --
    -- Nome explícito de propósito: a migration que a introduziu
    -- (20261030100000_us20_return_models.sql) nomeia assim, e um nome gerado
    -- pelo PostgreSQL faria os dois caminhos produzirem schemas diferentes.
    CONSTRAINT uq_sale_items_company_sale_id UNIQUE (company_id, sale_id, id)
);
CREATE INDEX idx_sale_items_sale ON public.sale_items (sale_id);
CREATE INDEX idx_sale_items_company ON public.sale_items (company_id);

-- Carimbo de conclusão. `sales.status` diz em que estado a venda está AGORA;
-- esta tabela diz quando e por quem ela foi fechada, e sobrevive a uma
-- reabertura ou cancelamento posterior.
CREATE TABLE public.sales_log (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id  uuid NOT NULL REFERENCES public.company(id) ON DELETE CASCADE,
    -- Os dois aceitam nulo porque o banco implantado aceita (migration
    -- 20261012230316 criou a tabela assim). Quem grava é o gatilho de
    -- conclusão, que sempre informa os dois; o nulo é possibilidade do
    -- schema, não caminho da aplicação.
    sale_id     uuid REFERENCES public.sales(id) ON DELETE CASCADE,
    created_by  uuid,
    logged_on   timestamptz DEFAULT now()
);
CREATE INDEX idx_sales_log_sale ON public.sales_log (sale_id);

-- Liga a movimentação de saída à venda que a gerou. Fica aqui, e não em
-- tables/05_movements.sql, porque `sales` só existe a partir deste arquivo na
-- ordem de schema_paths.
ALTER TABLE public.stock_movements
    ADD COLUMN sale_id uuid REFERENCES public.sales(id) ON DELETE SET NULL,
    ADD COLUMN sale_item_id uuid REFERENCES public.sale_items(id) ON DELETE SET NULL;
CREATE INDEX idx_stock_movements_sale ON public.stock_movements (sale_id);

-- Vínculo entre a venda original e a operação que a desfez (US17).
--
-- Tabela, e não colunas em `sales`: o vínculo é uma RELAÇÃO com autor,
-- motivo e instante próprios. Como atributo do cabeçalho ele engordaria a
-- cada motivo novo e não teria onde guardar autoria separada da autoria da
-- venda. É o mesmo papel que `sales_log` cumpre para a conclusão.
CREATE TABLE public.sale_reversals (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Redundante com sales.company_id, e proposital: a policy escopa por
    -- esta coluna sem entrar em `sales` a cada linha, como em sale_items.
    company_id  uuid NOT NULL,
    sale_id     uuid NOT NULL,
    kind        public.sale_reversal_kind NOT NULL,
    reason      text NOT NULL CHECK (btrim(reason) <> ''),
    -- Sem FK, como sales.created_by: a autoria da reversão precisa
    -- sobreviver à remoção da conta que a fez.
    created_by  uuid,
    created_on  timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (company_id, sale_id)
        REFERENCES public.sales (company_id, id) ON DELETE CASCADE,
    -- Reversão é TERMINAL: venda cancelada não vira devolvida depois, nem
    -- acumula reversões. As funções conferem também, mas é este índice que
    -- torna a regra verdadeira para quem chegue por outro caminho.
    UNIQUE (sale_id)
);
CREATE INDEX idx_sale_reversals_company ON public.sale_reversals (company_id);

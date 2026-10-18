-- Movimentações de estoque. Depende de company (01_identity) e products
-- (03_catalog).
--
-- O saldo de um produto é a SOMA DAS MOVIMENTAÇÕES CONFIRMADAS, não um número
-- digitado: é o que a US03 exige ao dizer "considerar somente movimentações
-- confirmadas na composição do saldo". `products.stock` continua existindo
-- como valor materializado, mantido pelo trigger em triggers/04.

CREATE TYPE public.movement_kind   AS ENUM ('ENTRADA', 'SAIDA');
CREATE TYPE public.movement_status AS ENUM ('PENDENTE', 'CONFIRMADA', 'CANCELADA');

-- Motivo de um ajuste manual de inventário (H11). Lista fechada, e não texto
-- livre: "quanto sumiu por quebra neste mês" tem que ser consulta, e motivo
-- inválido tem que ser erro de tipo, não string que ninguém lê.
CREATE TYPE public.adjustment_reason AS ENUM
    ('CONTAGEM', 'QUEBRA', 'PERDA', 'VENCIMENTO', 'DEVOLUCAO', 'OUTRO');

CREATE TABLE public.stock_movements (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Redundante com `products.company_id`, e proposital: a policy de RLS
    -- escopa por esta coluna sem precisar entrar em `products` a cada linha.
    company_id   uuid NOT NULL REFERENCES public.company(id) ON DELETE CASCADE,
    product_id   uuid NOT NULL REFERENCES public.products(id) ON DELETE CASCADE,
    kind         public.movement_kind   NOT NULL,
    quantity     integer NOT NULL CHECK (quantity > 0),
    -- Nasce PENDENTE: registrar não é confirmar. É essa distinção que a US03
    -- pede ao dizer "somente movimentações confirmadas".
    status       public.movement_status NOT NULL DEFAULT 'PENDENTE',
    note         text,
    created_by   uuid,
    created_on   timestamptz NOT NULL DEFAULT now(),
    confirmed_on timestamptz,

    -- H11. NULL = movimentação comum; preenchido = ajuste manual. Marca, e
    -- não espécie nova: um `AJUSTE` de quantidade com sinal exigiria
    -- derrubar o `CHECK (quantity > 0)` acima e reescrever o `CASE` de
    -- fn_confirmed_balance.
    adjustment_reason public.adjustment_reason,
    -- O saldo que o operador AFIRMOU ter contado. Guardado, e não só
    -- validado na gravação, para que um relatório de reconciliação consiga
    -- reconferir a invariante depois em vez de confiar nela.
    counted_balance   integer,
    sale_id uuid REFERENCES public.sales(id) ON DELETE SET NULL,
    sale_item_id uuid REFERENCES public.sale_items(id) ON DELETE SET NULL,

    -- Constraint NOMEADA, e não um CHECK inline: a migration precisa criá-la
    -- com guarda sobre `pg_constraint`, e isso exige um nome. Deixar o
    -- Postgres gerar o nome aqui faria os dois lados declararem a mesma
    -- regra com identidades diferentes, e o `declarative sync` seguinte
    -- proporia mexer nela.
    CONSTRAINT ck_movements_counted_balance CHECK (
        counted_balance IS NULL OR counted_balance >= 0),

    -- Os dois andam juntos: motivo sem contagem é ajuste sem número, e
    -- contagem sem motivo é ajuste sem justificativa.
    CONSTRAINT ck_movements_adjustment_pair CHECK (
        (adjustment_reason IS NULL     AND counted_balance IS NULL)
     OR (adjustment_reason IS NOT NULL AND counted_balance IS NOT NULL)),

    -- A justificativa é regra do BANCO. Quem chamar a função por SQL direto
    -- também é recusado.
    CONSTRAINT ck_movements_adjustment_detail CHECK (
        adjustment_reason IS DISTINCT FROM 'OUTRO'
     OR btrim(coalesce(note, '')) <> '')
);

CREATE INDEX idx_stock_movements_product
    ON public.stock_movements (product_id, status);
CREATE INDEX idx_stock_movements_company
    ON public.stock_movements (company_id);

-- Parcial, no molde de idx_stock_movements_supplier: o relatório de ajustes
-- percorre uma fração minúscula da tabela, e o índice cheio pagaria por
-- todas as movimentações comuns para servir essa fração.
CREATE INDEX idx_stock_movements_adjustment
    ON public.stock_movements (company_id, created_on)
    WHERE adjustment_reason IS NOT NULL;

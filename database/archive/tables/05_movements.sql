-- Movimentações de estoque. Depende de company (01_identity) e products
-- (03_catalog).
--
-- O saldo de um produto é a SOMA DAS MOVIMENTAÇÕES CONFIRMADAS, não um número
-- digitado: é o que a US03 exige ao dizer "considerar somente movimentações
-- confirmadas na composição do saldo". `products.stock` continua existindo
-- como valor materializado, mantido pelo trigger em triggers/04.

CREATE TYPE public.movement_kind   AS ENUM ('ENTRADA', 'SAIDA');
CREATE TYPE public.movement_status AS ENUM ('PENDENTE', 'CONFIRMADA', 'CANCELADA');

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
    confirmed_on timestamptz
);

CREATE INDEX idx_stock_movements_product
    ON public.stock_movements (product_id, status);
CREATE INDEX idx_stock_movements_company
    ON public.stock_movements (company_id);

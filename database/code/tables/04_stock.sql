-- Estoque mínimo por produto. Depende de products (03_catalog).

CREATE TYPE public.stock_state         AS ENUM ('CRITICO', 'BAIXO', 'ATENCAO', 'NORMAL');
CREATE TYPE public.company_stock_state AS ENUM ('CRITICO', 'ALERTA', 'ATENCAO', 'SEGURO');

CREATE TABLE public.product_stock (
    product_id    uuid PRIMARY KEY REFERENCES public.products(id) ON DELETE CASCADE,
    -- Sem NOT NULL e sem DEFAULT de propósito: NULL é "mínimo não
    -- configurado" e zero é um mínimo configurado como zero, que alerta
    -- quando o saldo zera. Com DEFAULT 0 todo produto novo nasceria com
    -- mínimo zero explícito e entraria no alerta sem ninguém ter pedido.
    -- O CHECK continua valendo: NULL >= 0 é unknown, e CHECK só reprova false.
    min_quantity  integer CHECK (min_quantity >= 0),
    updated_on    timestamptz NOT NULL DEFAULT now()
);

-- US20, etapa 1: modelo e leitura segura. Não instala RPCs nem emissão fiscal.
-- Reversionada antes da primeira aplicação, conforme confirmação do usuário.
-- Na sequência integrada, sucede 20261029130000_us22_sales_discounts.sql.
-- Incremental sobre o histórico versionado, que ainda não contém estas tabelas.
-- Não é idempotente: objetos homônimos preexistentes exigem reconciliação antes da aplicação.
BEGIN;

ALTER TABLE public.sale_items
    ADD CONSTRAINT uq_sale_items_company_sale_id UNIQUE (company_id, sale_id, id);

CREATE TYPE public.return_status AS ENUM ('PENDING', 'COMPLETED', 'CANCELLED');

CREATE TABLE public.returns (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id    uuid NOT NULL,
    sale_id       uuid NOT NULL,
    user_id       uuid NOT NULL,
    reason        text NOT NULL CHECK (btrim(reason) <> ''),
    total_amount  numeric(12,2) NOT NULL DEFAULT 0 CHECK (total_amount >= 0),
    status        public.return_status NOT NULL DEFAULT 'PENDING',
    created_on    timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_returns_company_sale FOREIGN KEY (company_id, sale_id)
        REFERENCES public.sales (company_id, id) ON DELETE RESTRICT,
    CONSTRAINT uq_returns_company_sale_id UNIQUE (company_id, sale_id, id)
);
CREATE INDEX idx_returns_company ON public.returns (company_id);
CREATE INDEX idx_returns_sale ON public.returns (sale_id);

CREATE TABLE public.return_items (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id    uuid NOT NULL,
    sale_id       uuid NOT NULL,
    return_id     uuid NOT NULL,
    sale_item_id  uuid NOT NULL,
    quantity      integer NOT NULL CHECK (quantity > 0),
    unit_price    numeric(10,2) NOT NULL CHECK (unit_price >= 0),
    discount      numeric(12,2) NOT NULL DEFAULT 0 CHECK (discount >= 0),
    subtotal      numeric(12,2) NOT NULL CHECK (subtotal >= 0),
    created_on    timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_return_items_return FOREIGN KEY (company_id, sale_id, return_id)
        REFERENCES public.returns (company_id, sale_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_return_items_sale_item FOREIGN KEY (company_id, sale_id, sale_item_id)
        REFERENCES public.sale_items (company_id, sale_id, id) ON DELETE RESTRICT,
    CONSTRAINT uq_return_items_return_sale_item UNIQUE (return_id, sale_item_id),
    CONSTRAINT ck_return_items_discount CHECK (discount <= quantity::numeric * unit_price),
    CONSTRAINT ck_return_items_subtotal CHECK (subtotal = quantity::numeric * unit_price - discount)
);
CREATE INDEX idx_return_items_return ON public.return_items (return_id);
CREATE INDEX idx_return_items_sale_item ON public.return_items (sale_item_id);
CREATE INDEX idx_return_items_company ON public.return_items (company_id);

ALTER TABLE public.returns ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.return_items ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.returns, public.return_items
  FROM PUBLIC, anon, authenticated, app_backend;
GRANT SELECT ON public.returns, public.return_items TO app_backend, authenticated;

CREATE POLICY returns_select ON public.returns
  FOR SELECT TO app_backend, authenticated
  USING (public.fn_is_member(company_id));
CREATE POLICY return_items_select ON public.return_items
  FOR SELECT TO app_backend, authenticated
  USING (public.fn_is_member(company_id));

COMMIT;

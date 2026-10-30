-- ------------------------------------------------------------
-- Tabela de devoluções (cabeçalho)
-- ------------------------------------------------------------

CREATE TYPE public.return_status AS ENUM (
    'PENDING',
    'COMPLETED',
    'CANCELLED'
);

CREATE TABLE public.returns (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id    uuid NOT NULL,
    sale_id       uuid NOT NULL,
    -- Autoria obrigatória, sem FK de conta: preserva o histórico, como sales.created_by.
    user_id       uuid NOT NULL,
    reason        text NOT NULL CONSTRAINT ck_returns_reason CHECK (reason ~ '[^[:space:]]'),
    total_amount  numeric(12,2) NOT NULL DEFAULT 0 CHECK (total_amount >= 0),
    status        public.return_status NOT NULL DEFAULT 'PENDING',
    created_on    timestamptz NOT NULL DEFAULT now(),
    -- NULL somente para registros anteriores ao contrato idempotente.
    idempotency_key uuid,
    request_payload jsonb,
    result_payload jsonb,
    CONSTRAINT uq_returns_company_idempotency UNIQUE (company_id, idempotency_key),
    CONSTRAINT ck_returns_idempotency CHECK (
        (idempotency_key IS NULL AND request_payload IS NULL AND result_payload IS NULL)
        OR (idempotency_key IS NOT NULL AND request_payload IS NOT NULL
            AND jsonb_typeof(request_payload) = 'object'
            AND (result_payload IS NULL OR jsonb_typeof(result_payload) = 'object'))
    ),
    -- A emissão fiscal pertence ao backend PHP; não há disparo fiscal no banco.
    CONSTRAINT fk_returns_company_sale FOREIGN KEY (company_id, sale_id)
        REFERENCES public.sales (company_id, id) ON DELETE RESTRICT,
    CONSTRAINT uq_returns_company_sale_id UNIQUE (company_id, sale_id, id)
);

CREATE INDEX idx_returns_company ON public.returns (company_id);
CREATE INDEX idx_returns_sale    ON public.returns (sale_id);

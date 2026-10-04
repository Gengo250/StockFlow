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

CREATE TABLE public.sales (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id       uuid NOT NULL REFERENCES public.company(id) ON DELETE CASCADE,
    client_id        uuid NOT NULL,
    product_id       uuid,
    client_name      text NOT NULL,
    product_name     text NOT NULL,
    product_code     text NOT NULL,
    total            numeric(10,2) NOT NULL CHECK (total >= 0),
    created_by       uuid,
    created_on       timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (company_id, client_id)
        REFERENCES public.clients (company_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (product_id)
        REFERENCES public.products (id) ON DELETE SET NULL
);
CREATE INDEX idx_sales_company_created
    ON public.sales (company_id, created_on DESC);

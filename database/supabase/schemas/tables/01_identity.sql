-- Empresas, contas de usuário e o vínculo entre as duas.
-- Precisa vir antes de catalog: products referencia company.

CREATE TYPE public.user_role AS ENUM ('ADMIN', 'STOCK', 'SELLER');

CREATE TABLE public.company (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name        text NOT NULL CHECK (btrim(name) <> ''),
    cnpj        text UNIQUE,
    active      boolean NOT NULL DEFAULT true,
    created_on  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE public.user_accounts (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name        text NOT NULL UNIQUE
                CHECK (name = lower(btrim(name)) AND length(name) >= 3),
    pass_hash   text NOT NULL
                CHECK (left(pass_hash, 1) = '$' AND length(pass_hash) >= 20),
    created_on  timestamptz NOT NULL DEFAULT now(),
    updated_on  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE public.company_users (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id       uuid NOT NULL REFERENCES public.company(id) ON DELETE CASCADE,
    user_account_id  uuid NOT NULL REFERENCES public.user_accounts(id) ON DELETE CASCADE,
    role             public.user_role NOT NULL DEFAULT 'STOCK',
    active           boolean NOT NULL DEFAULT true,
    created_on       timestamptz NOT NULL DEFAULT now(),
    updated_on       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (company_id, user_account_id)
);
CREATE INDEX idx_company_users_user ON public.company_users (user_account_id);

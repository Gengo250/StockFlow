CREATE TYPE public.user_role AS ENUM ('ADMIN', 'STOCK', 'SELLER');
CREATE TABLE public.company (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name        text NOT NULL,
    cnpj        text UNIQUE,
    active      boolean NOT NULL DEFAULT true,
    created_on  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE public.user_accounts (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name        text UNIQUE NOT NULL, 
    pass_hash   text NOT NULL,       
    created_on  timestamptz NOT NULL DEFAULT now(),
    updated_on  timestamptz NOT NULL DEFAULT now()
);



CREATE TABLE public.company_users (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id         uuid NOT NULL REFERENCES public.company(id) ON DELETE CASCADE,
    user_account_id uuid NOT NULL REFERENCES public.user_accounts(id) ON DELETE CASCADE,
    role               public.user_role NOT NULL DEFAULT 'STOCK',
    active             boolean NOT NULL DEFAULT true,
    created_on         timestamptz NOT NULL DEFAULT now(),
    updated_on         timestamptz NOT NULL DEFAULT now(),
    UNIQUE (company_id, user_account_id)
);


-- Primitivas sem dependência de outras funções.
-- São LANGUAGE sql, cujo corpo o Postgres valida na criação: tudo que elas
-- chamam precisa existir antes, por isso vêm primeiro.

CREATE OR REPLACE FUNCTION public.fn_current_user_id()
RETURNS uuid
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public, extensions AS $$
    SELECT NULLIF(current_setting('app.user_id', true), '')::uuid;
$$;

CREATE OR REPLACE FUNCTION public.fn_is_valid_pass_hash(p_hash text)
RETURNS boolean
LANGUAGE sql IMMUTABLE AS $$
    SELECT p_hash IS NOT NULL AND left(p_hash, 1) = '$' AND length(p_hash) >= 20;
$$;

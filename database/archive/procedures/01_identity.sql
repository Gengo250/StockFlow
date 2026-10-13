-- Primitivas sem dependência de outras funções.
-- São LANGUAGE sql, cujo corpo o Postgres valida na criação: tudo que elas
-- chamam precisa existir antes, por isso vêm primeiro.

-- Usuário corrente, resolvido por DOIS caminhos nesta ordem:
--
--   1. JWT do Supabase Auth: `auth.uid()` traduzido para o id de domínio
--      por `user_accounts.auth_user_id`, que é o que `company_users`
--      referencia. É o caminho do cliente REST (app desktop), que não tem
--      como definir parâmetro de sessão.
--   2. GUC `app.user_id`: o caminho de um backend dono da conexão, que faz
--      `SET app.user_id` após autenticar.
--
-- O JWT vem primeiro porque é identidade provada pelo Supabase; o GUC é só um
-- parâmetro de sessão. Invertido, uma sessão autenticada com o parâmetro
-- definido por acidente responderia pelo outro usuário.
CREATE OR REPLACE FUNCTION public.fn_current_user_id()
RETURNS uuid
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public, extensions AS $$
    SELECT COALESCE(
        (SELECT ua.id
           FROM public.user_accounts ua
          WHERE ua.auth_user_id = auth.uid()),
        NULLIF(current_setting('app.user_id', true), '')::uuid
    );
$$;

CREATE OR REPLACE FUNCTION public.fn_is_valid_pass_hash(p_hash text)
RETURNS boolean
LANGUAGE sql IMMUTABLE AS $$
    SELECT p_hash IS NOT NULL AND left(p_hash, 1) = '$' AND length(p_hash) >= 20;
$$;

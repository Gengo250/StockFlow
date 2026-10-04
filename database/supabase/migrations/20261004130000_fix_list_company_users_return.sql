-- Corrige "structure of query does not match function result type" em
-- `fn_list_company_users`, fixando explicitamente o tipo das colunas que vêm
-- do schema `auth`.
--
-- CAUSA
--
-- A função declara `login text`, mas alimenta essa coluna com
-- `COALESCE(au.email, ua.name)`, e `auth.users.email` é
-- `character varying(255)` no Supabase.
--
-- `COALESCE(varchar, text)` NÃO resolve para `text` sozinho. Pela regra de
-- `select_common_type` do Postgres, o tipo candidato só é trocado quando o
-- candidato atual é implicitamente conversível para o outro E o contrário não
-- é verdade. Entre `varchar` e `text` a conversão é implícita nos DOIS
-- sentidos, então a troca não acontece e o candidato continua `varchar` — o
-- primeiro argumento. O `RETURN QUERY` então entrega `varchar` onde o
-- descritor da função espera `text`, e o PL/pgSQL recusa a tupla inteira.
--
-- O erro aparece só na EXECUÇÃO, nunca na criação: `CREATE FUNCTION` não
-- valida o corpo de plpgsql. Por isso a migration anterior aplicou sem
-- reclamar e a falha surgiu no primeiro login de um ADMIN.
--
-- ESCOPO DA CORREÇÃO
--
-- Só os `::text` abaixo. Assinatura, ordem das colunas, STABLE,
-- SECURITY DEFINER, search_path, a checagem de `fn_is_admin`, os joins, o
-- filtro e as permissões ficam idênticos — `CREATE OR REPLACE` preserva os
-- grants porque o tipo de retorno não muda.
--
-- As duas expressões convertidas são exatamente as que leem `auth.users`, um
-- schema gerido pelo Supabase cujos tipos podem mudar entre versões da
-- plataforma sem aviso. Fixar o tipo na fronteira é o que impede que a
-- próxima mudança de lá derrube esta função de novo. `cd.department` e as
-- demais colunas vêm de tabelas nossas e continuam sem cast.

CREATE OR REPLACE FUNCTION public.fn_list_company_users(p_company_id uuid)
RETURNS TABLE (
    user_id      uuid,
    login        text,
    display_name text,
    department   text,
    user_role    public.user_role,
    is_active    boolean,
    last_access  timestamptz,
    created_on   timestamptz
)
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = public AS $$
BEGIN
    IF NOT public.fn_is_admin(public.fn_current_user_id(), p_company_id) THEN
        RAISE EXCEPTION 'Apenas administradores podem listar usuários'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    RETURN QUERY
    SELECT
        ua.id,
        -- O e-mail do Auth é o que a tela chama de "login" e o que o usuário
        -- digita para entrar. `user_accounts.name` é o login LOCAL (minúsculo,
        -- sem espaço) e só aparece enquanto a conta não foi vinculada.
        --
        -- O `::text` é a correção: sem ele o COALESCE devolve o
        -- `varchar(255)` de `auth.users.email`.
        COALESCE(au.email, ua.name)::text,
        -- Nome de exibição: metadado do Auth, com o login local como último
        -- recurso. `user_accounts.name` tem CHECK de minúsculo, então ele
        -- nunca é um nome próprio bem formatado.
        --
        -- Hoje `->>` já devolve `text` e o cast é redundante; ele fica porque
        -- a expressão depende de `auth.users`, e o contrato desta coluna não
        -- deve mudar junto com a plataforma.
        COALESCE(
            NULLIF(btrim(au.raw_user_meta_data->>'name'), ''),
            NULLIF(btrim(au.raw_user_meta_data->>'full_name'), ''),
            ua.name
        )::text,
        cd.department,
        cd.role,
        cd.active,
        au.last_sign_in_at,
        cd.created_on
      FROM public.company_users cd
      JOIN public.user_accounts ua ON ua.id = cd.user_account_id
      -- Junção pela esquerda: conta ainda não vinculada ao Auth continua
      -- aparecendo na lista, sem e-mail e sem último acesso. Escondê-la
      -- deixaria o administrador sem ver exatamente quem precisa de
      -- providência.
      LEFT JOIN auth.users au ON au.id = ua.auth_user_id
     WHERE cd.company_id = p_company_id
     ORDER BY 3;
END;
$$;

-- `CREATE OR REPLACE` mantém dono e privilégios quando a assinatura não muda,
-- mas o GRANT é refeito de qualquer forma: custa nada e protege o caso de a
-- função ter sido recriada à mão entre as migrations.
--
-- Nunca para PUBLIC nem anon — ver 20261004120000_revoke_public_execute.sql.
GRANT EXECUTE ON FUNCTION public.fn_list_company_users(uuid)
  TO app_backend, authenticated;

-- Liga uma conta do Supabase Auth a um usuário do StockFlow.
--
-- Rode VOCÊ, no SQL Editor do painel do Supabase, depois de:
--   1. aplicar 20261003180000_auth_jwt_identity.sql;
--   2. criar o usuário no Authentication > Users (ou por convite).
--
-- Criar a conta só no Auth NÃO basta. O Auth responde "quem é você"; quem
-- responde "o que você pode fazer" é `company_users`, e quem liga os dois é
-- `user_accounts.auth_user_id`. Sem as três pontas, o login até autentica e
-- para logo depois, na montagem da sessão.

-- ============================================================ 0. DIAGNÓSTICO
-- Rode isto primeiro. Mostra o que já existe e o que falta.

SELECT
    au.email,
    au.id                        AS auth_user_id,
    ua.name                      AS login_no_stockflow,
    ua.id                        AS user_account_id,
    cu.company_id,
    cu.role,
    cu.active                    AS acesso_ativo,
    CASE
        WHEN ua.id IS NULL THEN 'FALTA: linha em user_accounts'
        WHEN ua.auth_user_id IS NULL THEN 'FALTA: vínculo auth_user_id'
        WHEN cu.id IS NULL THEN 'FALTA: acesso em company_users'
        WHEN NOT cu.active THEN 'FALTA: acesso está inativo'
        ELSE 'OK — pode entrar'
    END                          AS situacao
  FROM auth.users au
  LEFT JOIN public.user_accounts ua ON ua.auth_user_id = au.id
  LEFT JOIN public.company_users cu ON cu.user_account_id = ua.id
 WHERE au.email = 'teste.stockflow@gmail.com';

-- Empresas disponíveis, para escolher o company_id do passo 2.
-- Se vier vazio, não há empresa nenhuma. Para criar empresa e ADMIN de uma vez:
--
--   SELECT public.fn_register_company(
--     'Minha Empresa', NULL, 'miguel',
--     extensions.crypt(gen_random_uuid()::text, extensions.gen_salt('bf')));
--
-- Atenção: ela cria a linha em `user_accounts` para o login informado SEM
-- `auth_user_id`. Se usar este caminho, pule o INSERT do passo 1 e rode só o
-- UPDATE de vínculo que está logo abaixo dele.
SELECT id, name, cnpj, active FROM public.company ORDER BY name;


-- ===================================================== 1. CONTA DE DOMÍNIO
-- Cria a linha em user_accounts já vinculada ao Auth.
--
-- `name` é o LOGIN, não o nome de exibição: a tabela tem
-- CHECK (name = lower(btrim(name)) AND length(name) >= 3), então 'Miguel'
-- seria recusado e 'miguel' passa. O nome que aparece na barra lateral vem
-- do metadado `name` do Supabase Auth, não daqui.
--
-- `pass_hash` é NOT NULL e exige um hash de verdade
-- (CHECK left(pass_hash,1) = '$' AND length(pass_hash) >= 20), mesmo com a
-- senha vivendo no Auth. Gerar o hash de um uuid aleatório deixa a coluna
-- válida e a senha LOCAL inutilizável de propósito: ninguém conhece o texto
-- de origem, então não existe segunda porta de entrada ignorando o Auth.

INSERT INTO public.user_accounts (name, pass_hash, auth_user_id)
SELECT
    'miguel',
    extensions.crypt(gen_random_uuid()::text, extensions.gen_salt('bf')),
    au.id
  FROM auth.users au
 WHERE au.email = 'teste.stockflow@gmail.com'
ON CONFLICT (name) DO UPDATE
    SET auth_user_id = EXCLUDED.auth_user_id;   -- conta já existia: só vincula

-- Se o `crypt`/`gen_salt` acima reclamar de função inexistente, o pgcrypto do
-- seu projeto não está no schema `extensions`. Tente sem o prefixo
-- (`crypt(...)`, `gen_salt('bf')`) ou instale com
-- `CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA extensions;`.

-- Vínculo isolado, para quando a linha em `user_accounts` já existe — por
-- exemplo criada por `fn_register_company`:
--
--   UPDATE public.user_accounts ua
--      SET auth_user_id = au.id
--     FROM auth.users au
--    WHERE au.email = 'teste.stockflow@gmail.com'
--      AND ua.name  = 'miguel';


-- ======================================================== 2. ACESSO E PAPEL
-- Dá o papel ao usuário dentro de uma empresa.
--
-- TROQUE o company_id abaixo por um da consulta do passo 0.
-- Papéis: 'ADMIN' (tudo, inclusive administrar usuários),
--         'STOCK' (cadastra e edita produto), 'SELLER' (só vende).

INSERT INTO public.company_users (company_id, user_account_id, role, active)
SELECT
    'COLE-AQUI-O-UUID-DA-EMPRESA'::uuid,
    ua.id,
    'ADMIN'::public.user_role,
    true
  FROM public.user_accounts ua
 WHERE ua.name = 'miguel'
ON CONFLICT (company_id, user_account_id) DO UPDATE
    SET role = EXCLUDED.role, active = true;


-- ============================================================ 3. CONFERÊNCIA
-- Rode a consulta do passo 0 de novo: `situacao` precisa dizer "OK — pode
-- entrar". Só então:
--
--     STOCKFLOW_BACKEND=supabase uv run stockflow
--
-- A tela de USUÁRIOS passou a ler `fn_list_company_users`: com o backend
-- ligado, `miguel` aparece lá, e o subtítulo diz "Dados da empresa" em vez de
-- "Dados demonstrativos". Ela exige a migration 20261004090000_user_directory
-- além da de identidade.
--
-- Como a lista interpreta o que você provisionou aqui:
--   "Pendente" = conta ativa que NUNCA entrou (auth.users.last_sign_in_at
--                nulo). É o estado normal logo após o provisionamento.
--   "Inativo"  = company_users.active = false.
--   e-mail em branco e nome em minúsculo = falta o vínculo `auth_user_id`.

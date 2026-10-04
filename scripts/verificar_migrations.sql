-- O que o banco REALMENTE tem, comparado ao que as migrations deveriam ter
-- criado. Rode no SQL Editor do Supabase.
--
-- Serve para responder "a migration pegou?" sem depender da aplicação: a
-- chave publicável se conecta como `anon`, que não tem privilégio nenhum, e
-- por isso o diagnóstico de fora não consegue distinguir "não aplicou" de
-- "aplicou e está recusando corretamente".

-- =================================================== 1. COLUNAS ESPERADAS

SELECT
    esperado.tabela,
    esperado.coluna,
    CASE WHEN c.column_name IS NULL THEN '✗ FALTA' ELSE '✓ ok' END AS situacao,
    esperado.migration
  FROM (VALUES
      ('user_accounts', 'auth_user_id', '20261003180000_auth_jwt_identity'),
      ('company_users', 'department',   '20261004090000_user_directory')
  ) AS esperado(tabela, coluna, migration)
  LEFT JOIN information_schema.columns c
         ON c.table_schema = 'public'
        AND c.table_name   = esperado.tabela
        AND c.column_name  = esperado.coluna
 ORDER BY 1, 2;


-- ================================================== 2. FUNÇÕES ESPERADAS

SELECT
    esperado.funcao,
    CASE WHEN p.oid IS NULL THEN '✗ FALTA' ELSE '✓ ok' END AS situacao,
    esperado.migration
  FROM (VALUES
      ('fn_current_user_id',             '20261003180000_auth_jwt_identity'),
      ('fn_my_companies',                'pré-existente'),
      ('fn_list_company_users',          '20261004090000_user_directory (recriada)'),
      ('fn_set_company_user_department', '20261004090000_user_directory (nova)')
  ) AS esperado(funcao, migration)
  LEFT JOIN pg_proc p
         ON p.pronamespace = 'public'::regnamespace
        AND p.proname = esperado.funcao
 ORDER BY 1;


-- ========================================== 3. A LISTAGEM TEM AS COLUNAS NOVAS?
--
-- `fn_list_company_users` existia antes com cinco colunas de retorno. Se a
-- migration do diretório não pegou, ela continua existindo — mas SEM
-- display_name, department e last_access, e a tela de Usuários quebraria ao
-- procurar por eles.

SELECT
    p.proname,
    pg_get_function_result(p.oid) AS retorno,
    CASE WHEN pg_get_function_result(p.oid) LIKE '%last_access%'
         THEN '✓ versão do diretório'
         ELSE '✗ versão ANTIGA — 20261004090000 não pegou'
    END AS situacao
  FROM pg_proc p
 WHERE p.pronamespace = 'public'::regnamespace
   AND p.proname = 'fn_list_company_users';


-- ======================================= 4. QUEM PODE EXECUTAR CADA FUNÇÃO
--
-- O desenho é: `app_backend` e `authenticated` executam a allowlist; `anon` e
-- `PUBLIC` não executam NADA. Qualquer linha com `anon` ou `PUBLIC` abaixo é
-- um buraco.
--
-- Causa conhecida: função criada por uma migration POSTERIOR à de segurança
-- nasce com EXECUTE para PUBLIC (padrão do Postgres), e a varredura de REVOKE
-- daquela migration já tinha passado. Foi o que aconteceu com
-- `fn_update_products` (criada em 20261003120200, depois de 20261003120100).

SELECT
    p.proname AS funcao,
    COALESCE(string_agg(DISTINCT a.grantee, ', ' ORDER BY a.grantee), '(ninguém)') AS pode_executar,
    CASE WHEN bool_or(a.grantee IN ('PUBLIC', 'anon'))
         THEN '✗ ABERTA DEMAIS'
         ELSE '✓ ok'
    END AS situacao
  FROM pg_proc p
  LEFT JOIN LATERAL aclexplode(COALESCE(p.proacl, acldefault('f', p.proowner))) acl ON true
  LEFT JOIN LATERAL (
      SELECT CASE WHEN acl.grantee = 0 THEN 'PUBLIC'
                  ELSE pg_get_userbyid(acl.grantee) END AS grantee
       WHERE acl.privilege_type = 'EXECUTE'
  ) a ON true
 WHERE p.pronamespace = 'public'::regnamespace
   AND p.prokind = 'f'
   AND p.proname LIKE 'fn\_%'
 GROUP BY p.proname
 ORDER BY 3 DESC, 1;


-- ================================================ 5. MIGRATIONS REGISTRADAS
--
-- Só existe se você aplica pelo Supabase CLI (`supabase db push`). Aplicando
-- pelo SQL Editor, esta tabela não registra nada — e nesse caso o veredito
-- são as consultas 1 a 4 acima, não esta.

SELECT version, name
  FROM supabase_migrations.schema_migrations
 WHERE version >= '20261003120000'
 ORDER BY version;

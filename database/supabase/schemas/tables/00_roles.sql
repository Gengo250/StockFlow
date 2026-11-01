-- ------------------------------------------------------------
-- Papel da aplicação, criado ANTES de qualquer coisa que conceda a ele
-- ------------------------------------------------------------
--
-- Este arquivo não declara tabela. Ele mora em `tables/` porque esse é o
-- primeiro grupo de `schema_paths`, e `00_` o coloca antes de
-- `01_identity.sql`: é a única posição da ordem declarativa que roda antes de
-- todo o resto.
--
-- Por que precisa existir aqui. Quatro arquivos concedem privilégio a
-- `app_backend` antes do grupo `policies/`:
--
--     procedures/08_return_partial.sql
--     procedures/09_get_returnable_items.sql
--     triggers/05_role_change_log.sql
--     triggers/09_sale_return_guard.sql
--
-- e quem criava o papel era `policies/01_security.sql`, que roda por último.
-- Aplicar `database/code/` num cluster limpo parava em
--
--     role "app_backend" does not exist
--
-- O defeito ficou invisível por muito tempo porque papel no PostgreSQL é do
-- CLUSTER, não do banco: quem já tivesse rodado as migrations na mesma
-- instância tinha `app_backend` de pé, e o declarativo parecia aplicar. Só um
-- cluster recém-criado expõe isso — foi a CI, na primeira execução com
-- PostgreSQL de verdade, que pegou.
--
-- O bloco idempotente continua em `policies/01_security.sql` de propósito:
-- aquele arquivo precisa continuar legível sozinho como a declaração completa
-- do modelo de segurança, e repetir uma guarda `IF NOT EXISTS` não custa nada.

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_backend') THEN
    CREATE ROLE app_backend NOLOGIN NOINHERIT;
  END IF;
END $$;

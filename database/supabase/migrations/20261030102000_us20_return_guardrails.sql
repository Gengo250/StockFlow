-- US20: alinhar leitura por RLS à autorização ADMIN das RPCs e rejeitar
-- motivos compostos somente por whitespace. Migração corretiva incremental:
-- mantém as correções separadas das etapas anteriores, sem alterar seus corpos.
-- Depende de 20261030101000_us20_return_rpcs.sql. Reversionada antes da primeira
-- aplicação para não colidir com a US22; o corpo SQL permanece preservado.
BEGIN;

DROP POLICY IF EXISTS returns_select ON public.returns;
CREATE POLICY returns_select ON public.returns
  FOR SELECT TO app_backend, authenticated
  USING (public.fn_has_role(company_id, ARRAY['ADMIN']::public.user_role[]));

DROP POLICY IF EXISTS return_items_select ON public.return_items;
CREATE POLICY return_items_select ON public.return_items
  FOR SELECT TO app_backend, authenticated
  USING (public.fn_has_role(company_id, ARRAY['ADMIN']::public.user_role[]));

ALTER TABLE public.returns
    DROP CONSTRAINT IF EXISTS returns_reason_check,
    ADD CONSTRAINT ck_returns_reason CHECK (reason ~ '[^[:space:]]');

COMMIT;

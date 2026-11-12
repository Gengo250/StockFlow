-- US24: Registrar eventos imutáveis de auditoria.
--
-- Cria tabela audit_log para persistência de eventos de auditoria com autor,
-- data/hora, ação, entidade, id e estados anterior/novo.
-- Garante imutabilidade estrita via trigger que proíbe UPDATE e DELETE.

BEGIN;

CREATE TABLE IF NOT EXISTS public.audit_log (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid REFERENCES public.company(id) ON DELETE CASCADE,
    user_id text NOT NULL,
    action text NOT NULL,
    entity text NOT NULL,
    entity_id text NOT NULL,
    old_values jsonb,
    new_values jsonb,
    is_critical boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audit_log_company ON public.audit_log(company_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_entity ON public.audit_log(entity, entity_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_created_at ON public.audit_log(created_at DESC);

-- Função e trigger que bloqueiam UPDATE e DELETE
CREATE OR REPLACE FUNCTION public.trg_prevent_audit_modification()
RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Registros de auditoria são imutáveis e não podem ser editados ou excluídos'
        USING ERRCODE = 'check_violation';
END;
$$;

DROP TRIGGER IF EXISTS trg_audit_log_immutable ON public.audit_log;
CREATE TRIGGER trg_audit_log_immutable
    BEFORE UPDATE OR DELETE ON public.audit_log
    FOR EACH ROW EXECUTE FUNCTION public.trg_prevent_audit_modification();

REVOKE ALL ON FUNCTION public.trg_prevent_audit_modification()
    FROM PUBLIC, anon, authenticated, app_backend;

-- Políticas de segurança e controle de acesso
ALTER TABLE public.audit_log ENABLE ROW LEVEL SECURITY;

GRANT SELECT, INSERT ON TABLE public.audit_log TO app_backend, authenticated;

DROP POLICY IF EXISTS audit_log_select ON public.audit_log;
DROP POLICY IF EXISTS audit_log_insert ON public.audit_log;

CREATE POLICY audit_log_select ON public.audit_log
    FOR SELECT TO app_backend, authenticated
    USING (company_id IS NULL OR public.fn_has_role(company_id, ARRAY['ADMIN']::public.user_role[]));

CREATE POLICY audit_log_insert ON public.audit_log
    FOR INSERT TO app_backend, authenticated
    WITH CHECK (true);

NOTIFY pgrst, 'reload schema';

COMMIT;

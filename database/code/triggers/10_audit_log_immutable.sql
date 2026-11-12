-- Imutabilidade estrita dos registros de auditoria (US24).
-- Registros de auditoria não podem ser editados ou excluídos pela aplicação nem por comandos SQL diretos.
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

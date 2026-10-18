-- H13: preservar os dados originais, mesmo após cancelamento.
CREATE OR REPLACE FUNCTION public.trg_protect_confirmed_movement()
RETURNS trigger LANGUAGE plpgsql
SET search_path = public AS $$
BEGIN
    IF OLD.status = 'CONFIRMADA' OR OLD.confirmed_on IS NOT NULL THEN
        IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'Movimentação confirmada não pode ser excluída; utilize o cancelamento'
                USING ERRCODE = 'check_violation';
        END IF;
        IF (to_jsonb(NEW) - 'status') IS DISTINCT FROM (to_jsonb(OLD) - 'status')
           OR NEW.status NOT IN ('CONFIRMADA', 'CANCELADA')
           OR (OLD.status = 'CANCELADA' AND NEW.status <> 'CANCELADA') THEN
            RAISE EXCEPTION 'Movimentação confirmada não pode ser editada; utilize o cancelamento'
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_protect_confirmed_movement ON public.stock_movements;
CREATE TRIGGER trg_protect_confirmed_movement
    BEFORE UPDATE OR DELETE ON public.stock_movements
    FOR EACH ROW EXECUTE FUNCTION public.trg_protect_confirmed_movement();

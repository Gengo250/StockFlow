-- H13: bloquear edição/exclusão sem remover o cancelamento auditável.
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

CREATE OR REPLACE FUNCTION public.fn_register_supplier_movement(
    p_company_id uuid,
    p_product_id uuid,
    p_kind public.movement_kind,
    p_quantity integer,
    p_supplier_id uuid,
    p_note text DEFAULT NULL,
    p_confirm boolean DEFAULT false
) RETURNS uuid
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = public AS $$
DECLARE
    v_id uuid;
BEGIN
    IF p_kind <> 'ENTRADA' THEN
        RAISE EXCEPTION 'Fornecedor só pode ser associado a uma entrada'
            USING ERRCODE = 'invalid_parameter_value';
    END IF;
    IF NOT public.fn_has_role(p_company_id, ARRAY['ADMIN','STOCK']::public.user_role[]) THEN
        RAISE EXCEPTION 'Sem permissão para registrar compras nesta empresa'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF p_supplier_id IS NULL OR NOT EXISTS (
        SELECT 1 FROM public.suppliers
         WHERE id = p_supplier_id AND company_id = p_company_id AND active
    ) THEN
        RAISE EXCEPTION 'Fornecedor obrigatório, ativo e da empresa é necessário'
            USING ERRCODE = 'foreign_key_violation';
    END IF;

    v_id := public.fn_register_movement(
        p_company_id, p_product_id, p_kind, p_quantity, p_note, false
    );
    UPDATE public.stock_movements SET supplier_id = p_supplier_id WHERE id = v_id;
    IF p_confirm THEN
        PERFORM public.fn_confirm_movement(v_id);
    END IF;
    RETURN v_id;
END;
$$;

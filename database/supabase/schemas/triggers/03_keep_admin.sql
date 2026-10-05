-- Impede que uma empresa fique sem administrador ativo.
--
-- A regra vale para TODA porta de administração — `fn_toggle_company_user`,
-- `fn_save_company_member` e qualquer UPDATE/DELETE futuro — por isso mora
-- aqui e não dentro de cada função.
--
-- O `FOR UPDATE` na empresa serializa as portas concorrentes: sem ele, duas
-- transações rebaixando administradores diferentes ao mesmo tempo leem a
-- contagem antiga uma da outra e as duas passam, deixando a empresa sem
-- nenhum ADMIN ativo.
CREATE OR REPLACE FUNCTION public.trg_company_users_keep_admin()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path = public AS $$
BEGIN
    IF OLD.role = 'ADMIN' AND OLD.active
       AND (TG_OP = 'DELETE' OR NEW.role <> 'ADMIN' OR NOT NEW.active)
    THEN
        -- Trava a empresa antes de contar. FOUND falso significa empresa
        -- removida: é o DELETE em cascata, que não deve ser barrado.
        PERFORM 1 FROM public.company WHERE id = OLD.company_id FOR UPDATE;
        IF FOUND AND NOT EXISTS (
            SELECT 1 FROM public.company_users cd
             WHERE cd.company_id = OLD.company_id AND cd.id <> OLD.id
               AND cd.role = 'ADMIN' AND cd.active
        ) THEN
            RAISE EXCEPTION 'A empresa precisa manter ao menos um administrador ativo'
                USING ERRCODE = 'restrict_violation';
        END IF;
    END IF;
    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END;
$$;

CREATE TRIGGER trg_company_users_keep_admin BEFORE UPDATE OR DELETE ON public.company_users
    FOR EACH ROW EXECUTE FUNCTION public.trg_company_users_keep_admin();

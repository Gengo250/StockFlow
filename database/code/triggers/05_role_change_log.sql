-- Registra toda atribuição de perfil e toda mudança de acesso (H14).
--
-- Mora num trigger pelo mesmo motivo de triggers/03_keep_admin.sql: a regra
-- precisa valer para TODA porta que mexe em company_users. Hoje são três
-- funções distintas — fn_save_company_member, fn_update_company_user e
-- fn_toggle_company_user — mais fn_create_company_user e fn_register_company
-- na criação do vínculo. Instrumentar uma a uma deixaria buracos, e o próximo
-- caminho de escrita nasceria sem auditoria nenhuma.
--
-- SECURITY DEFINER é o que permite gravar no log sem dar INSERT à role da
-- aplicação: o dono da função alcança a tabela, e `app_backend` continua sem
-- nenhuma porta de escrita ali.
CREATE OR REPLACE FUNCTION public.trg_company_users_log_role()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path = public AS $$
BEGIN
    -- Edição que não toca em papel nem em acesso não é evento de permissão.
    -- Sem esta saída, corrigir um departamento ou um nome de exibição
    -- encheria a auditoria de linhas em que nada mudou.
    IF TG_OP = 'UPDATE'
       AND NEW.role = OLD.role
       AND NEW.active IS NOT DISTINCT FROM OLD.active THEN
        RETURN NEW;
    END IF;

    INSERT INTO public.role_change_log (
        company_id, actor_id, target_user_id,
        role_before, role_after, active_before, active_after
    ) VALUES (
        NEW.company_id,
        public.fn_current_user_id(),
        NEW.user_account_id,
        CASE WHEN TG_OP = 'UPDATE' THEN OLD.role END,
        NEW.role,
        CASE WHEN TG_OP = 'UPDATE' THEN OLD.active END,
        NEW.active
    );

    RETURN NEW;
END;
$$;

-- AFTER, e não BEFORE: só interessa registrar o que de fato passou pelas
-- checagens. O trigger de keep_admin é BEFORE e aborta a transação quando a
-- empresa ficaria sem administrador; um log em BEFORE registraria uma
-- promoção que nunca aconteceu.
CREATE TRIGGER trg_company_users_log_role
    AFTER INSERT OR UPDATE ON public.company_users
    FOR EACH ROW EXECUTE FUNCTION public.trg_company_users_log_role();

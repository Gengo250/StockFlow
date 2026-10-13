-- Histórico de atribuição de perfil e de acesso (H14).
-- Depende de company e user_accounts (01_identity) e do tipo user_role.
--
-- A história pede que "as operações relevantes registrem o usuário
-- autenticado". Para perfil e acesso, uma coluna `updated_by` em
-- `company_users` não serviria: ela guarda só o último autor, e a pergunta que
-- importa numa auditoria de permissão é "quem promoveu esta pessoa a ADMIN, e
-- quando" — que exige histórico, não o estado atual.
--
-- Escrita exclusivamente pelo trigger de triggers/05_role_change_log.sql.
-- A aplicação não recebe INSERT aqui, de propósito: log que o próprio sistema
-- auditado pode escrever à mão não é evidência de nada.
CREATE TABLE public.role_change_log (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id     uuid NOT NULL REFERENCES public.company(id) ON DELETE CASCADE,
    -- Quem fez a mudança, por fn_current_user_id(). Nullable porque o
    -- primeiro ADMIN de uma empresa nasce em fn_register_company, antes de
    -- existir sessão: nesse instante não há autor, e inventar um seria pior
    -- do que registrar a ausência.
    actor_id       uuid,
    -- Sem FK para user_accounts, igual a stock_movements.created_by e
    -- sales.created_by. Aqui o motivo é mais forte: com ON DELETE CASCADE o
    -- log sumiria junto com o usuário que ele descreve, e um histórico que
    -- desaparece quando o investigado é removido não audita coisa alguma.
    target_user_id uuid NOT NULL,
    -- NULL no vínculo recém-criado: não havia papel anterior.
    role_before    public.user_role,
    role_after     public.user_role NOT NULL,
    active_before  boolean,
    active_after   boolean NOT NULL,
    changed_on     timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_role_change_log_company
    ON public.role_change_log (company_id, changed_on DESC);
CREATE INDEX idx_role_change_log_target
    ON public.role_change_log (target_user_id);

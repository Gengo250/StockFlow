-- Corrige o EXECUTE para PUBLIC nas funções da US17.
--
-- 20261024120000 criou fn_list_sales, fn_cancel_sale e fn_return_sale e deu
-- GRANT aos papéis certos, mas sem REVOGAR de PUBLIC antes. Função nova em
-- PostgreSQL nasce com EXECUTE para PUBLIC, e o
-- `ALTER DEFAULT PRIVILEGES ... REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC, anon`
-- de 20261004120000 só vale para o papel que o executou — não para o papel
-- que aplica esta cadeia.
--
-- É o MESMO buraco que `fn_update_products` abriu e que
-- `policies/01_security.sql` documenta: "toda migration que criar função nova
-- precisa repetir a varredura". A fonte declarativa já está correta porque a
-- varredura roda no fim dela; quem ficou de fora foi o caminho das migrations,
-- que é justamente o que o remoto usa.
--
-- Não houve exposição de dado: as três funções conferem `fn_is_member` ou
-- `fn_has_role` na primeira instrução, então o anônimo levava 42501 de dentro.
-- Isto fecha a camada de fora, que é onde a recusa deveria acontecer primeiro.
--
-- POR QUE VARREDURA, E NÃO REVOKE POR ASSINATURA
--
-- A primeira redação deste arquivo revogava por assinatura literal. Num
-- remoto onde 20261024120000 constava como aplicada mas as funções não
-- existiam, ela morreu com `42883 function ... does not exist` — um erro que
-- aponta para o REVOKE e esconde o problema real, que era a ausência da
-- função. A varredura resolve a assinatura a partir do catálogo, então vale
-- para qualquer forma que a função tenha, e o bloco seguinte transforma a
-- ausência numa mensagem que diz o que de fato falta.

DO $$
DECLARE
  r record;
BEGIN
  FOR r IN SELECT p.oid::regprocedure AS assinatura
             FROM pg_proc p
             JOIN pg_namespace n ON n.oid = p.pronamespace
            WHERE n.nspname = 'public'
              AND p.proname IN ('fn_list_sales', 'fn_cancel_sale', 'fn_return_sale')
  LOOP
    EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC, anon', r.assinatura);
    EXECUTE format(
      'GRANT EXECUTE ON FUNCTION %s TO app_backend, authenticated', r.assinatura);
  END LOOP;
END $$;

-- Falha ALTO e nomeando o que falta, em vez de deixar a aplicação descobrir
-- em runtime que a tela de Vendas não tem função para chamar. Mesmo padrão
-- do `RAISE EXCEPTION 'Funções obrigatórias ausentes'` de policies/01.
DO $$
DECLARE
  v_esperadas text[] := ARRAY['fn_list_sales', 'fn_cancel_sale', 'fn_return_sale'];
  v_faltando  text[];
BEGIN
  SELECT array_agg(nome ORDER BY nome) INTO v_faltando
    FROM unnest(v_esperadas) AS nome
   WHERE NOT EXISTS (
     SELECT 1 FROM pg_proc p
       JOIN pg_namespace n ON n.oid = p.pronamespace
      WHERE n.nspname = 'public' AND p.proname = nome
   );

  IF v_faltando IS NOT NULL THEN
    RAISE EXCEPTION
      'Funções da US17 ausentes no banco: %. A migration 20261024120000 '
      'consta como aplicada mas não as criou; reaplique-a antes desta.',
      array_to_string(v_faltando, ', ');
  END IF;
END $$;

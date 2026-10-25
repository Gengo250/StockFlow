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

REVOKE ALL ON FUNCTION public.fn_list_sales(
    uuid, text, timestamptz, timestamptz, uuid, uuid,
    public.sale_status, text, integer, integer
) FROM PUBLIC, anon;

REVOKE ALL ON FUNCTION public.fn_cancel_sale(uuid, text) FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION public.fn_return_sale(uuid, text) FROM PUBLIC, anon;

-- Repete o GRANT: o REVOKE de PUBLIC não tira o que foi concedido
-- nominalmente, mas repetir aqui torna o estado final legível num arquivo só.
GRANT EXECUTE ON FUNCTION public.fn_list_sales(
    uuid, text, timestamptz, timestamptz, uuid, uuid,
    public.sale_status, text, integer, integer
) TO app_backend, authenticated;

GRANT EXECUTE ON FUNCTION public.fn_cancel_sale(uuid, text) TO app_backend, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_return_sale(uuid, text) TO app_backend, authenticated;

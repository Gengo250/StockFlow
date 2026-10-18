-- Preserva a auditoria de preços introduzida pelo histórico remoto.

-- Qual campo a linha descreve (H09). Lista fechada, como adjustment_reason:
-- campo auditado em texto livre aceitaria 'sell_price', 'SELLPRICE' e 'venda'
-- na mesma coluna, e "histórico do preço de venda" deixaria de ser consulta
-- para virar leitura.
CREATE TYPE public.price_edit_field AS ENUM ('SELL_PRICE', 'BUY_PRICE');

CREATE TABLE IF NOT EXISTS public.price_edit_log (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    updated_by uuid,
    company_id uuid NOT NULL REFERENCES public.company(id) ON DELETE CASCADE,
    last_updated_on timestamptz NOT NULL DEFAULT now(),
    -- Venda e custo dividem o par antes/depois porque a pergunta é a mesma; o
    -- que muda é o campo, e é esta coluna que o nomeia. O DEFAULT não é
    -- conveniência: toda linha que já existe no remoto veio de `sell_price`,
    -- e é ele que as mantém legíveis depois da coluna entrar.
    field public.price_edit_field NOT NULL DEFAULT 'SELL_PRICE',
    -- Nullable de propósito, porque `products.buy_price` é nullable
    -- (tables/03_catalog.sql): informar o custo pela primeira vez tem
    -- `OLD.buy_price IS NULL`. Com o par obrigatório, o INSERT desta auditoria
    -- violaria NOT NULL e derrubaria o UPDATE do produto — a auditoria
    -- impediria a edição que ela existe para registrar. Gravar `0` no lugar
    -- inventaria um custo que nunca foi praticado.
    old_price numeric,
    new_price numeric,
    product_id uuid NOT NULL REFERENCES public.products(id) ON DELETE CASCADE,
    -- Os dois lados nulos descreveriam uma mudança sem valor nenhum.
    CONSTRAINT ck_price_edit_log_value_present
        CHECK (old_price IS NOT NULL OR new_price IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS idx_price_edit_log_product_id ON public.price_edit_log(product_id);
CREATE INDEX IF NOT EXISTS idx_price_edit_log_company_id ON public.price_edit_log(company_id);

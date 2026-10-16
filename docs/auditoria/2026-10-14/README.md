# Fechamento da correção de vendas — 14/10/2026

Implementação e validação local concluídas. Aplicação no Supabase remoto
pendente. Após o login do responsável, a listagem e o dry-run confirmaram as
três migrações esperadas. Nenhuma migration remota foi aplicada nesta sessão.

## Comportamento entregue

- Finalizar vende todos os itens do carrinho e inclui o produto selecionado,
  respeitando quantidade, pagamento e desconto. Quantidade vazia equivale a 1.
- O preço unitário vem do catálogo. Alterar o catálogo atualiza a prévia do
  carrinho; o resultado da venda usa o recibo produzido na transação do banco,
  inclusive se o preço mudar em outra sessão antes da gravação.
- Recarregar o histórico conserva itens, quantidades, preços, pagamento e
  desconto. Os detalhes dos produtos aparecem na dica da coluna Produto.
- Durante a gravação, o envio duplicado fica bloqueado. Na recusa, o carrinho
  permanece disponível para correção e nova tentativa.
- Concluir a venda gera saídas confirmadas e atualiza o estoque. Falta de saldo
  desfaz a venda inteira; duas vendas concorrentes não consomem o mesmo saldo.
- A conversão incremental preserva cabeçalhos, itens, autores e logs antigos,
  sem repetir baixas históricas. Quantidades históricas fracionárias interrompem
  a conversão, sem arredondar ou apagar dados.
- A reconciliação declarativa preserva a auditoria de preços e restringe sua
  leitura a administradores da empresa. A entrada legada de estoque sem guarda
  de papel foi retirada; a aplicação já usa as funções autorizadas de movimentos.

## Evidências

| Verificação | Resultado |
| --- | --- |
| `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -q --tb=short` | 784 passed, 1 skipped, 103,18 s |
| `.venv/bin/python scripts/verify_postgres.py` | 59 arquivos de migration aplicados; fluxo Qt, persistência, permissões e estoque passaram |
| `.venv/bin/python scripts/verify_postgres.py --schema` | 30 arquivos declarativos aplicados; mesmos fluxos passaram |
| `.venv/bin/python scripts/verify_sales.py` | Conversão dos modelos remoto/US07, preservação, rollback, checkout Qt, RLS e concorrência passaram |
| Capturas da janela | 1024×768 e 1440×900; finalizar continua visível e o formulário tem rolagem |

O skip existente corresponde ao ADMIN, que alcança todas as áreas e não tem
uma área negada para aquele caso parametrizado de navegação.

PostgreSQL **16.2 real**, com `pgcrypto`, executado em servidor local descartável
na porta 55439. O pacote `pgserver` não incluía essa extensão: foi compilado o
PostgreSQL oficial em diretório temporário, sem extensão falsa nem alteração
do cache do pacote. Os verificadores só aceitam localhost e criam/removem seus
próprios bancos `stockflow_verify_*`. Supabase Auth e HTTP/PostgREST não são
testados nesses scripts; eles usam uma representação local de `auth.uid()` e
uma ponte de consultas para dirigir a UI contra SQL real.

Capturas: [1024×768](vendas-1024.png) e [1440×900](vendas-1440.png).

## Aplicação no Supabase

Executar os comandos abaixo **na raiz `StockFlow/`**. Se o terminal já estiver
em `StockFlow/database/`, substituir `--workdir database` por `--workdir .`;
repetir `database` procuraria o vínculo em `database/database/`.

Após autenticar a CLI no ambiente do responsável:

```bash
supabase login
supabase migration list --workdir database
supabase db push --workdir database --include-all --skip-vault --dry-run
```

Conjunto confirmado pela listagem e pelo dry-run remoto em 14/10:

1. `20261013120000_h14_role_permissions_model.sql`.
2. `20261013140000_us09_us10_sale_items_and_stock_link.sql`, com conversão incremental.
3. `20261014120000_reconcile_sales_schema.sql`, reconciliação final desta retomada.

O dry-run confirmou apenas esse conjunto, sem seeds nem roles adicionais.
Ele não executa nem comprova a aplicação do SQL. `--include-all` permite a H14 cujo timestamp é anterior a
migrations remotas já existentes. Se aparecerem migrations históricas além
desse conjunto, reconciliar o histórico antes: em particular,
`20261010231302_customer_orders.sql` contém um `DROP TABLE sales CASCADE`
histórico e não deve ser reaplicada sobre dados existentes.

Após conferir que a lista contém somente as atualizações esperadas:

```bash
supabase db push --workdir database --include-all --skip-vault
STOCKFLOW_BACKEND=supabase uv run stockflow
```

Confirmar na UI uma venda com dois produtos, quantidade maior que 1, PIX e
desconto; recarregar o histórico e consultar Estoque. A conclusão no remoto
depende dessa aplicação e verificação, não dos testes locais.

## Correção posterior: 25P01 no `db push`

A primeira tentativa de aplicação real parou na segunda migration:

```
Applying migration 20261013140000_us09_us10_sale_items_and_stock_link.sql...
ERROR: LOCK TABLE can only be used in transaction blocks (SQLSTATE 25P01)
At statement: 0
```

`supabase db push` manda cada comando da migration separadamente, em
autocommit: não existe transação envolvendo o arquivo. O `LOCK TABLE` da
primeira linha é recusado nesse modo. A verificação local não pegou porque
`scripts/verify_postgres.py` aplicava cada arquivo já dentro de uma transação
própria — o contrato do verificador era mais generoso que o do aplicador real.

Três mudanças:

1. As duas migrations ainda não aplicadas abrem a própria transação (`BEGIN;`
   na primeira linha executável, `COMMIT;` na última). Em
   `20261013140000_us09_us10_sale_items_and_stock_link.sql` isso torna o `LOCK`
   válido e devolve ao arquivo o rollback que os comentários dele já assumiam —
   sem transação, uma falha no meio deixaria a conversão de `sale_items` pela
   metade no remoto. Em `20261014120000_reconcile_sales_schema.sql` não havia
   `LOCK`, então ela não falhava; o `BEGIN` entra pelo mesmo motivo de
   integridade, para a auditoria de preços não ficar de pé sem a policy que
   restringe a leitura dela.
2. `scripts/verify_postgres.py` não envolve mais cada arquivo numa transação
   externa. O PostgreSQL já executa a string inteira numa transação implícita,
   e a camada extra brigaria com uma migration que abre a sua.
3. `tests/test_schema_declarativo.py` ganhou dois guardas estáticos: migration
   que usa `LOCK TABLE`/`SET CONSTRAINTS` precisa abrir `BEGIN;`/`COMMIT;`, e
   migration que abre transação não pode usar comando que o PostgreSQL recusa
   dentro de uma (`CONCURRENTLY`, `VACUUM`, `ALTER SYSTEM`, …).

A primeira migration (`20261013120000_h14_role_permissions_model.sql`) já
aparece como aplicada. Reaplicar o conjunto é seguro: as duas restantes são
idempotentes (`IF NOT EXISTS`, blocos `DO` com guarda, inserção de itens
filtrada por `NOT EXISTS`) e agora são tudo-ou-nada.

```bash
supabase db push --workdir database --include-all --skip-vault
```
